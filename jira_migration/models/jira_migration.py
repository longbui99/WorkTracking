import requests
import json
from urllib.parse import urlparse
from odoo.addons.project_management.utils.search_parser import get_search_request
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class JIRAMigration(models.Model):
    _name = 'jira.migration'
    _description = 'JIRA Migration'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence')
    jira_server_url = fields.Char(string='JIRA Server URL')
    import_work_log = fields.Boolean(string='Import Work Logs?')
    auto_export_work_log = fields.Boolean(string="Auto Export Work Logs?")

    def __get_request_headers(self):
        self.ensure_one()
        employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        if not employee_id:
            raise UserError(_("Don't have any related Employee, please set up on Employee Application"))
        if not employee_id.jira_private_key:
            raise UserError(_("Missing the Access token in the related Employee"))
        headers = {
            'Authorization': "Bearer " + employee_id.jira_private_key,
        }
        return headers

    def load_projects(self):
        headers = self.__get_request_headers()
        result = requests.get(f"{self.jira_server_url}/project", headers=headers)
        existing_project = self.env['jira.project'].search([])
        existing_project_dict = {f"{r.project_key}": True for r in existing_project}
        new_project = []
        for record in json.loads(result.text):
            if not existing_project_dict.get(record.get('key', False), False):
                new_project.append({
                    'project_name': record['name'],
                    'project_key': record['key'],
                })

        if new_project:
            self.env['jira.project'].create(new_project)

    @api.model
    def make_request(self, request_data, headers):
        endpoint = request_data.get('endpoint', None)
        if not endpoint:
            return {}
        if 'params' in request_data:
            endpoint += "?" + '&'.join(request_data['params'])
        body = "{}"
        if 'body' in request_data:
            body = json.dumps(request_data['body'])
        if request_data.get('method', 'get') in ['post', 'put']:
            headers.update({'Content-Type': 'application/json'})
        method = getattr(requests, request_data.get('method', 'get'))
        result = method(url=endpoint, headers=headers, data=body)
        body = result.json()
        if body.get('errorMessages', False):
            raise UserError("Jira Server: \n" + "\n".join(body['errorMessages']))
        return body

    # ===========================================  Section for loading tickets/issues =============================================

    @api.model
    def __load_from_key_paths(self, object, paths):
        res = object
        for key in paths:
            if key in res and res.get(key) is not None:
                res = res[key]
            else:
                return None
        return res

    def get_local_issue_data(self, domain=[]):
        return {
            'project_key_dict': {r.project_key: r.id for r in self.env['jira.project'].sudo().search([])},
            'dict_user': {r.partner_id.email: r.id for r in self.env['res.users'].sudo().search([])},
            'dict_ticket_key': {r.ticket_key: r for r in self.env['jira.ticket'].sudo().search(domain)},
            'dict_status': {r.key: r.id for r in self.env['jira.status'].sudo().search([])},
        }

    def processing_issue_raw_data(self, local, raw):
        response = []
        for ticket in raw.get('issues', [raw]):
            ticket_fields = ticket['fields']
            status = self.__load_from_key_paths(ticket_fields, ['status', 'id'])
            story_point = ticket_fields.get('customfield_10008', 0.0) or 0.0
            assignee = self.__load_from_key_paths(ticket_fields, ['assignee', 'key'])
            project = self.__load_from_key_paths(ticket_fields, ['project', 'key'])
            server_url = urlparse(self.jira_server_url).netloc
            map_url = (lambda r: f"https://{server_url}/browse/{r}")
            if ticket.get('key', '-') not in local['dict_ticket_key']:
                if not ticket_fields:
                    continue
                res = {
                    'ticket_name': ticket_fields['summary'],
                    'ticket_key': ticket['key'],
                    'ticket_url': map_url(ticket['key']),
                    'story_point': story_point,
                    'jira_migration_id': self.id,
                    'create_date': ticket_fields['created']
                }
                if local['project_key_dict'].get(project, False):
                    res['project_id'] = local['project_key_dict'][project]
                if local['dict_user'].get(assignee, False):
                    res['assignee_id'] = local['dict_user'][assignee]
                if local['dict_status'].get(status, False):
                    res['status_id'] = local['dict_status'][status]
                else:
                    new_status = self.__load_from_key_paths(ticket_fields, ['status'])
                    status_id = self.env['jira.status'].create({
                        'name': new_status['name'],
                        'key': new_status['id'],
                        'jira_key': self.__load_from_key_paths(ticket_fields, ['status', 'statusCategory', 'key'])
                    }).id
                    local['dict_status'][status] = status_id
                response.append(res)
            else:
                existing_record = local['dict_ticket_key'][ticket.get('key', '-')]
                update_dict = {
                    'story_point': story_point,
                }
                if existing_record.status_id.id != local['dict_status'][status]:
                    update_dict['status_id'] = local['dict_status'][status]
                if assignee and assignee in local['dict_user'] and existing_record.assignee_id.id != local['dict_user'][
                    assignee]:
                    update_dict['assignee_id'] = local['dict_user'][assignee]
                existing_record.write(update_dict)
                if response and not isinstance(response[0], dict):
                    response[0] |= existing_record
                else:
                    response.insert(0, existing_record)
        return response

    def do_request(self, request_data, domain=[], paging=50, load_all=False):
        existing_record = self.env['jira.ticket']
        headers = self.__get_request_headers()
        start_index = 0
        total_response = paging
        response = []
        local_data = self.get_local_issue_data(domain)
        request_data['params'] = request_data.get('params', [])
        request = request_data.copy()

        while start_index < total_response:
            page_size = paging if total_response - start_index > paging else total_response - start_index
            params = request_data['params'].copy()
            params += [f'startAt={start_index}']
            params += [f'maxResult={page_size}']
            request['params'] = params
            body = self.make_request(request, headers)
            if body.get('total', 0) > total_response and load_all:
                total_response = body['total']
            start_index += paging
            new_tickets = self.processing_issue_raw_data(local_data, body)
            if new_tickets:
                if not isinstance(new_tickets[0], dict):
                    existing_record |= new_tickets[0]
                    new_tickets.pop(0)
            response.extend(new_tickets)
        return existing_record | self.env['jira.ticket'].create(response)

    def load_tickets(self, extra_jql="", domain=[], load_all=False):
        request_data = {
            'endpoint': f"{self.jira_server_url}/search",
            'params': [extra_jql]
        }
        return self.do_request(request_data, domain=domain, load_all=load_all)

    def load_all_tickets(self):
        return self.load_tickets(load_all=True)

    def load_my_tickets(self):
        extra_jql = f"""jql=assignee='{self.env.user.partner_id.email}' ORDER BY createdDate ASC"""
        ticket_ids = self.load_tickets(extra_jql, domain=[('assignee_id', '=', self.env.user.id)], load_all=True)
        if ticket_ids and self.import_work_log:
            for ticket_id in ticket_ids:
                self.with_delay().load_work_logs(ticket_id)

    def load_by_links(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("jira_migration.load_by_link_action_form")
        context = json.loads(action['context'])
        context.update({'default_migration_id': self.id})
        action['context'] = context
        return action

    @api.model
    def search_ticket(self, keyword):
        return self.search_load(keyword)

    def _search_load(self, type, params, is_my=False):
        ticket_ids = self.env['jira.ticket']
        if type == 'ticket':
            if not isinstance(params, (list, tuple)):
                params = [params]
            for key in params:
                request_data = {
                    'endpoint': f"{self.jira_server_url}/issue/{key.upper()}",
                }
                ticket_ids |= self.do_request(request_data, [('ticket_key', 'in', params)])
            self.load_work_logs(ticket_ids)
        elif type == 'project':
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [
                    f"""jql={' OR '.join(list(map(lambda x: f'project="{x}"', params)))} ORDER BY createdDate ASC"""
                ]
            }
            ticket_ids |= self.do_request(request_data, load_all=True)
            if ticket_ids and self.import_work_log:
                for ticket_id in ticket_ids:
                    self.with_delay().load_work_logs(ticket_id)
        elif type == "text":
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [
                    f"""jql=text~"{params}" {is_my and f' AND assignee="{self.env.user.partner_id.email}"' or ""} ORDER BY createdDate DESC"""
                ]
            }
            ticket_ids |= self.do_request(request_data, load_all=True)
            self.load_work_logs(ticket_ids)
        elif type == "project_text":
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [
                    f"""jql=project="{params[0]}" AND text~"{params[1]}" {is_my and f'AND assignee="{self.env.user.partner_id.email}"' or ""} ORDER BY createdDate ASC"""
                ]
            }
            ticket_ids |= self.do_request(request_data, load_all=True)
            self.load_work_logs(ticket_ids)
        elif type == "jql":
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [params]
            }
            ticket_ids |= self.do_request(request_data, load_all=True)
            self.load_work_logs(ticket_ids)
        return ticket_ids

    def search_load(self, payload):
        is_my = payload.startswith("my-")
        if is_my:
            payload = payload[3:]
        type, params = get_search_request(payload)
        return self._search_load(type, params, is_my)

    # ===========================================  Section for loading work logs ===================================
    def get_local_worklog_data(self, ticket_id, domain):
        return {
            'work_logs': {x.id_on_jira: x for x in ticket_id.time_log_ids if x.id_on_jira},
            'ticket_id': ticket_id,
            'dict_user': {r.partner_id.email: r.id for r in self.env['res.users'].sudo().search([])},
        }

    def update_work_log_data(self, log_id, data):
        to_update = {}
        work_log_id = data['work_logs'][log_id]
        if work_log_id.duration != data['timeSpentSeconds']:
            to_update['duration'] = data['timeSpentSeconds']
            to_update['time'] = data['timeSpent']
        logging_email = self.__load_from_key_paths(data, ['updateAuthor', 'key'])
        start_date = self.__load_from_key_paths(data, ['created'])
        if work_log_id.user_id.id != data['dict_user'].get(logging_email, False):
            to_update['user_id'] = data['dict_user'].get(logging_email, False)
        if not work_log_id.start_date or work_log_id.start_date.isoformat()[:16] != start_date[:16]:
            to_update['start_date'] = datetime.fromisoformat(start_date[:-5])
        if to_update:
            work_log_id.write(to_update)

    def processing_worklog_raw_data(self, data, body):
        new_tickets = []
        ticket_id = data['ticket_id']
        affected_jira_ids = set()
        for work_log in body.get('worklogs', [body]):
            log_id = int(work_log.get('id', '-'))
            affected_jira_ids.add(log_id)
            if log_id not in data['work_logs']:
                to_create = {
                    'time': work_log['timeSpent'],
                    'duration': work_log['timeSpentSeconds'],
                    'description': work_log['comment'],
                    'state': 'done',
                    'source': 'sync',
                    'ticket_id': ticket_id.id,
                    'id_on_jira': work_log['id'],
                    'start_date': datetime.fromisoformat(work_log['started'][:-5])
                }
                logging_email = self.__load_from_key_paths(work_log, ['updateAuthor', 'key'])
                to_create['user_id'] = data['dict_user'].get(logging_email, False)
                new_tickets.append(to_create)
            else:
                self.update_work_log_data(log_id, work_log)

        deleted = set(list(data['work_logs'].keys())) - affected_jira_ids
        if deleted:
            self.env['jira.time.log'].search([('id_on_jira', 'in', list(deleted))]).unlink()

        return new_tickets

    def load_work_logs(self, ticket_ids, paging=50, domain=[], load_all=False):
        if self.import_work_log:
            for ticket_id in ticket_ids:
                headers = self.__get_request_headers()
                request_data = {
                    'endpoint': f"{self.jira_server_url}/issue/{ticket_id.ticket_key}/worklog",
                }
                start_index = 0
                total_response = paging
                to_create = []
                local_data = self.get_local_worklog_data(ticket_id, domain)
                request_data['params'] = request_data.get('params', [])
                request = request_data.copy()
                while start_index < total_response:
                    page_size = paging if total_response - start_index > paging else total_response - start_index
                    params = request_data['params'].copy()
                    params += [f'startAt={start_index}']
                    params += [f'maxResult={page_size}']
                    request['params'] = params
                    body = self.make_request(request, headers)
                    if body.get('total', 0) > total_response and load_all:
                        total_response = body['total']
                    start_index += paging
                    new_tickets = self.processing_worklog_raw_data(local_data, body)
                    to_create.extend(new_tickets)
                if to_create:
                    self.env['jira.time.log'].create(to_create)

    @api.model
    def _get_time_log_payload(self, time_log_id):
        return {
            "comment": time_log_id.description,
            "started": time_log_id.start_date.isoformat(sep='T', timespec='milliseconds') + "+0000",
            "timeSpentSeconds": time_log_id.duration
        }

    def add_time_logs(self, ticket_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.jira_server_url}/issue/{ticket_id.ticket_key}/worklog",
            'method': 'post',
        }
        for log in time_log_ids:
            payload = self._get_time_log_payload(log)
            request_data['body'] = payload
            res = self.make_request(request_data, headers)
            log.id_on_jira = res['id']

    def update_time_logs(self, ticket_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.jira_server_url}/issue/{ticket_id.ticket_key}/worklog",
            'method': 'put',
        }
        for log in time_log_ids:
            try:
                payload = self._get_time_log_payload(log)
                request_data['body'] = payload
                request_clone = request_data.copy()
                request_clone['endpoint'] += f"/{log.id_on_jira}"
                res = self.make_request(request_clone, headers)
            except:
                continue

    def export_time_log(self, ticket_id):
        current_user_id = self.env.user.id
        time_log_to_create_ids = ticket_id.time_log_ids.filtered(lambda x: not x.id_on_jira)
        time_log_to_update_ids = ticket_id.time_log_ids.filtered(
            lambda x: x.id_on_jira
                      and (not ticket_id.last_export or x.write_date > ticket_id.last_export)
                      and (x.user_id.id == current_user_id)
        )
        self.add_time_logs(ticket_id, time_log_to_create_ids)
        self.update_time_logs(ticket_id, time_log_to_update_ids)
