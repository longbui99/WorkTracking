from cgi import test
import requests
import json
import pytz
import logging
import base64
from urllib.parse import urlparse
from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.jira_migration.utils.ac_parsing import parsing, unparsing
from odoo.addons.base.models.res_partner import _tz_get
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class JIRAMigration(models.Model):
    _name = 'jira.migration'
    _description = 'JIRA Migration'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence')
    timezone = fields.Selection(_tz_get, string='Timezone', default="UTC", required=True)
    jira_server_url = fields.Char(string='JIRA Server URL')
    auth_type = fields.Selection([('basic', 'Basic'), ('api_token', 'API Token')], string="Authentication Type", default="basic")
    import_work_log = fields.Boolean(string='Import Work Logs?')
    auto_export_work_log = fields.Boolean(string="Auto Export Work Logs?")
    is_load_acs = fields.Boolean(string="Import Acceptance Criteria?")
    jira_agile_url = fields.Char(string="JIRA Agile URL")
    admin_user_ids = fields.Many2many("res.users", string="Admins")

    def convert_server_tz_to_utc(self, timestamp):
        if not isinstance(timestamp, datetime):
            timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
        return timestamp.astimezone(pytz.utc).replace(tzinfo=None)

    def convert_utc_to_usertz(self, timestamp):
        if not isinstance(timestamp, datetime):
            timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z")
        return timestamp.astimezone(pytz.timezone(self.env.user.tz or 'UTC')).replace(tzinfo=None)

    def __get_request_headers(self):
        self.ensure_one()
        jira_private_key = self._context.get('access_token')
        if not jira_private_key:
            employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
            if not employee_id:
                raise UserError(_("Don't have any related Employee, please set up on Employee Application"))
            if not employee_id.jira_private_key:
                raise UserError(_("Missing the Access token in the related Employee"))
            jira_private_key = employee_id.jira_private_key
            if self.auth_type == 'api_token':
                jira_private_key = str(base64.encode(f"{self.env.user.partner_id.email}:{jira_private_key}"))

        headers = {
            'Authorization': "Bearer " + jira_private_key
        }
        return headers

    def _get_single_project(self, project_key):
        headers = self.__get_request_headers()
        result = requests.get(f"{self.jira_server_url}/project/{project_key}", headers=headers)
        record = json.loads(result.text)
        return self.env['jira.project'].create({
            'project_name': record['name'],
            'project_key': record['key'],
            'jira_migration_id': self.id
        }).id

    def _get_current_employee(self):
        return {
            "user_email": {user.partner_id.email or user.login for user in
                           self.with_context(active_test=False).env["res.users"].sudo().search([])}
        }

    def load_all_users(self, user_email=''):
        headers = self.__get_request_headers()
        current_employee_data = self._get_current_employee()
        result = requests.get(f'{self.jira_server_url}/user/search?startAt=0&maxResults=50000&username="{user_email}"',
                              headers=headers)
        records = json.loads(result.text)
        if not isinstance(records, list):
            records = [records]
        users = self.env["res.users"].sudo()
        for record in records:
            if record["name"] not in current_employee_data["user_email"]:
                users |= self.env["res.users"].create({
                    "name": record["displayName"],
                    "login": record["name"],
                    'active': False
                })

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
                    'jira_migration_id': self.id
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
        if result.text == "":
            return ""
        body = result.json()
        if body.get('errorMessages', False):
            raise UserError("Jira Server: \n" + "\n".join(body['errorMessages']))
        return body

    # ===========================================  Section for loading tickets/issues =============================================
    @api.model
    def _create_new_acs(self, values=[]):
        if not values:
            return []
        return list(map(lambda r: (0, 0, {
            'name': parsing(r["name"]),
            'jira_raw_name': r["name"],
            "checked": r["checked"],
            "key": r["id"],
            "sequence": r["rank"],
            "is_header": r["isHeader"]
        }), values))

    def _update_acs(self, ac_ids, values=[]):
        if not values:
            return False
        value_keys = {str(r['id']): r for r in values}
        existing_records = ac_ids.filtered(lambda r: r.key not in value_keys)
        ac_ids -= existing_records
        existing_records.unlink()
        for record in ac_ids:
            r = value_keys[record.key]
            record.write({
                'name': parsing(r["name"]),
                'jira_raw_name': r["name"],
                "checked": r["checked"] or record.checked,
                "key": r["id"],
                "sequence": r["rank"],
                "is_header": r["isHeader"]
            })
            del value_keys[record.key]
        res = self._create_new_acs(list(value_keys.values()))
        return res

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
            'dict_user': self.with_context(active_test=False).get_user(),
            'dict_ticket_key': {r.ticket_key: r for r in self.env['jira.ticket'].sudo().search(domain)},
            'dict_status': {r.key: r.id for r in self.env['jira.status'].sudo().search([])},
            'dict_type': {r.key: r.id for r in self.env["jira.type"].sudo().search([])}
        }

    def processing_issue_raw_data(self, local, raw):
        response = []
        load_ac = self.is_load_acs
        for ticket in raw.get('issues', [raw]):
            ticket_fields = ticket['fields']
            status = self.__load_from_key_paths(ticket_fields, ['status', 'id'])
            story_point = ticket_fields.get('customfield_10008')
            estimate_hour = ticket_fields.get('customfield_11102') or 0.0
            assignee = self.__load_from_key_paths(ticket_fields, ['assignee', 'name'])
            tester = self.__load_from_key_paths(ticket_fields, ['customfield_11101', 'name'])
            project = self.__load_from_key_paths(ticket_fields, ['project', 'key'])
            issue_type = self.__load_from_key_paths(ticket_fields, ['issuetype', 'id'])
            server_url = urlparse(self.jira_server_url).netloc
            map_url = (lambda r: f"https://{server_url}/browse/{r}")
            if ticket.get('key', '-') not in local['dict_ticket_key']:
                if not ticket_fields:
                    continue
                res = {
                    'ticket_name': ticket_fields['summary'],
                    'ticket_key': ticket['key'],
                    'ticket_url': map_url(ticket['key']),
                    'story_point': story_point and story_point or estimate_hour,
                    'jira_migration_id': self.id,
                    'create_date': ticket_fields['created']
                }
                if estimate_hour:
                    res['story_point_unit'] = 'hrs'
                if local['project_key_dict'].get(project, False):
                    res['project_id'] = local['project_key_dict'][project]
                else:
                    local['project_key_dict'][project] = self._get_single_project(project)
                    res['project_id'] = local['project_key_dict'][project]
                if local['dict_user'].get(assignee, False):
                    res['assignee_id'] = local['dict_user'][assignee]
                if local['dict_user'].get(tester, False):
                    res['tester_id'] = local['dict_user'][tester]
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
                    res['status_id'] = local['dict_status'][status]
                if local["dict_type"].get(issue_type, False):
                    res['ticket_type_id'] = local['dict_type'][issue_type]
                else:
                    new_issue_type = self.__load_from_key_paths(ticket_fields, ['issuetype'])
                    new_issue_type_id = self.env['jira.type'].create({
                        'name': new_issue_type['name'],
                        'img_url': new_issue_type['iconUrl'],
                        'key': issue_type
                    }).id
                    local['dict_type'][issue_type] = new_issue_type_id
                    res['ticket_type_id'] = local['dict_type'][issue_type]
                if load_ac:
                    res["ac_ids"] = self._create_new_acs(
                        self.__load_from_key_paths(ticket_fields, ['customfield_10206']))
                response.append(res)
            else:
                existing_record = local['dict_ticket_key'][ticket.get('key', '-')]
                update_dict = {
                    'story_point': story_point and story_point or estimate_hour,
                }
                if estimate_hour:
                    update_dict['story_point_unit'] = 'hrs'
                if existing_record.ticket_name != ticket_fields['summary']:
                    update_dict['ticket_name'] = ticket_fields['summary']
                if existing_record.status_id.id != local['dict_status'][status]:
                    update_dict['status_id'] = local['dict_status'][status]
                if existing_record.ticket_type_id.id != local['dict_type'][issue_type]:
                    update_dict['ticket_type_id'] = local['dict_type'][issue_type]
                if assignee and assignee in local['dict_user'] and existing_record.assignee_id.id != local['dict_user'][
                    assignee]:
                    update_dict['assignee_id'] = local['dict_user'][assignee]
                if tester and tester in local['dict_user'] and existing_record.tester_id.id != local['dict_user'][tester]:
                    update_dict['tester_id'] = local['dict_user'][tester]
                if load_ac:
                    res = self._update_acs(existing_record.ac_ids,
                                           self.__load_from_key_paths(ticket_fields, ['customfield_10206']))
                    if res:
                        update_dict['ac_ids'] = res
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

    def _search_load(self, res, delay=False):
        ticket_ids = self.env['jira.ticket']
        if 'ticket' in res:
            if not isinstance(res['ticket'], (list, tuple)):
                res['ticket'] = [res['ticket']]
            for key in res['ticket']:
                request_data = {
                    'endpoint': f"{self.jira_server_url}/issue/{key.upper()}",
                }
                ticket_ids |= self.do_request(request_data, [('ticket_key', 'in', res['ticket'])])
        else:
            params = []
            if 'project' in res:
                if not isinstance(res['project'], (list, tuple)):
                    res['project'] = [res['project']]
                params.append(' OR '.join(list(map(lambda x: f'project="{x}"', res['project']))))
            if "mine" in res:
                params.append(f'assignee="{self.env.user.partner_id.email}"')
            if "text" in res:
                params.append(f"""text~"{res['text']}""")
            if "jql" in res:
                params = [res["jql"]]
            if "sprint" in res:
                if "sprint+" == res['sprint']:
                    params.append("sprint in futureSprints()")
                else:
                    params.append("sprint in openSprints()")
            query = f"""jql={' AND '.join(params)}"""
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [query]
            }
            ticket_ids |= self.do_request(request_data, load_all=True)
        if delay:
            self.with_delay().load_work_logs(ticket_ids)
        else:
            self.load_work_logs(ticket_ids)

        return ticket_ids

    def search_load(self, payload):
        res = get_search_request(payload)
        return self._search_load(res)

    # ===========================================  Section for loading work logs ===================================
    def get_user(self):
        return {r.partner_id.email or r.login: r.id for r in self.env['res.users'].sudo().search([])}

    def get_local_worklog_data(self, ticket_id, domain):
        return {
            'work_logs': {x.id_on_jira: x for x in ticket_id.time_log_ids if x.id_on_jira},
            'ticket_id': ticket_id,
            'dict_user': self.with_context(active_test=False).get_user(),
        }

    def update_work_log_data(self, log_id, work_log, data):
        to_update = {}
        work_log_id = data['work_logs'][log_id]
        if work_log_id.duration != work_log['timeSpentSeconds']:
            to_update['duration'] = work_log['timeSpentSeconds']
            to_update['time'] = work_log['timeSpent']
        logging_email = self.__load_from_key_paths(work_log, ['updateAuthor', 'name'])
        start_date = self.convert_server_tz_to_utc(self.__load_from_key_paths(work_log, ['started']))
        if work_log_id.user_id.id != data['dict_user'].get(logging_email, False):
            to_update['user_id'] = data['dict_user'].get(logging_email, False)
        if not work_log_id.start_date or work_log_id.start_date.isoformat()[:16] != start_date.isoformat()[:16]:
            to_update['start_date'] = start_date
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
                    'start_date': self.convert_server_tz_to_utc(work_log['started'])
                }
                logging_email = self.__load_from_key_paths(work_log, ['updateAuthor', 'name'])
                to_create['user_id'] = data['dict_user'].get(logging_email, False)
                new_tickets.append(to_create)
            else:
                self.update_work_log_data(log_id, work_log, data)

        deleted = set(list(data['work_logs'].keys())) - affected_jira_ids
        if deleted:
            self.env['jira.time.log'].search([('id_on_jira', 'in', list(deleted))]).unlink()

        return new_tickets

    def load_work_logs(self, ticket_ids, paging=50, domain=[], load_all=False):
        if self.import_work_log:
            headers = self.__get_request_headers()
            for ticket_id in ticket_ids:
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
        time_log_to_create_ids = ticket_id.time_log_ids.filtered(lambda x: not x.id_on_jira and x.state == 'done')
        time_log_to_update_ids = ticket_id.time_log_ids.filtered(
            lambda x: x.id_on_jira
                      and (not ticket_id.last_export or x.write_date > ticket_id.last_export)
                      and (x.user_id.id == current_user_id)
                      and x.state == 'done'
        )
        self.add_time_logs(ticket_id, time_log_to_create_ids)
        self.update_time_logs(ticket_id, time_log_to_update_ids)

    def _update_project(self, project_id, access_token):
        self = self.with_context(access_token=access_token)
        updated_date = '0001-01-01'
        if project_id.last_update:
            updated_date = self.convert_utc_to_usertz(project_id.last_update).strftime('%Y-%m-%d %H:%M')
        params = f"""jql=project="{project_id.project_key}" AND updated >= '{updated_date}'"""
        request_data = {'endpoint': f"{self.jira_server_url}/search", "params": [params]}
        ticket_ids = self.do_request(request_data, load_all=True)
        self.load_work_logs(ticket_ids)
        project_id.last_update = datetime.now()
        self.load_sprints(project_id.board_ids)
        self.with_context(force=True).update_issue_for_sprints(project_id.sprint_ids)

    def update_project(self, project_id, access_token):
        self.with_delay()._update_project(project_id, access_token)

    def get_ac_payload(self, ticket_id):
        res = ticket_id.ac_ids.mapped(
            lambda r: {
                "name": r.jira_raw_name,
                "checked": r.checked,
                "rank": r.sequence,
                "isHeader": r.is_header,
                "id": int(r.key)
            }
        )
        res = {
            "fields": {
                "customfield_10206": res
            }
        }
        return res

    def export_acceptance_criteria(self, ticket_id):
        current_user_id = self.env.user.id
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.jira_server_url}/issue/{ticket_id.ticket_key}",
            'method': 'put',
        }
        payload = self.get_ac_payload(ticket_id)
        request_data['body'] = payload
        res = self.make_request(request_data, headers)
        return res

    # Agile Connection
    def load_boards(self, project_ids=False):
        if not self.jira_agile_url:
            return
        if not project_ids:
            project_ids = self.env["jira.project"].search([])
        headers = self.__get_request_headers()
        for project in project_ids:
            request_data = {
                'endpoint': f"""{self.jira_agile_url}/board?projectKeyOrId={project.project_key}""",
                'method': 'get',
            }
            current_boards = set(project.board_ids.mapped('id_on_jira'))
            try:
                data = self.make_request(request_data, headers)
                for board in data['values']:
                    if board['id'] not in current_boards:
                        self.env["board.board"].create({
                            'id_on_jira': board['id'],
                            'name': board['name'],
                            'type': board['type'],
                            'project_id': project.id
                        })
            except Exception as e:
                _logger.warning(f"Loading board on project {project.project_name} failed: " + str(e))

    def load_sprints(self, board_ids=False):
        if not self.jira_agile_url:
            return
        if not board_ids:
            board_ids = self.env['board.board'].search([('project_id.allowed_user_ids', '!=', False)])
        headers = self.__get_request_headers()
        for board in board_ids:
            if not board.id_on_jira and not board.type == 'scrum':
                continue
            request_data = {
                'endpoint': f"""{self.jira_agile_url}/board/{board.id_on_jira}/sprint?maxResults=200""",
                'method': 'get',
            }
            current_sprints = {x.id_on_jira: x for x in board.sprint_ids}
            try:
                data = self.make_request(request_data, headers)
                for sprint in data['values']:
                    if sprint['id'] not in current_sprints:
                        self.env["agile.sprint"].create({
                            'id_on_jira': sprint['id'],
                            'name': sprint['name'],
                            'state': sprint['state'],
                            'project_id': board.project_id.id,
                            'board_id': board.id,
                            'updated': True
                        })
                    elif sprint['state'] != current_sprints[sprint['id']].state:
                        current_sprints[sprint['id']].write({
                            'state': sprint['state'],
                            'updated': True
                        })
            except Exception as e:
                _logger.warning(f"Loading sprint on board {board.name} failed: " + str(e))

    def update_issue_for_sprints(self, sprint_ids=False):
        if not sprint_ids:
            sprint_ids = self.env["agile.sprint"].search([('state', 'in', ('active', 'future'))])
        headers = self.__get_request_headers()
        current_tickets = {x.ticket_key: x for x in self.env["jira.ticket"].search(
            [('create_date', '>', datetime.now() - relativedelta(months=2))])}
        force = self.env.context.get('force', False)
        for sprint in sprint_ids:
            if not sprint.id_on_jira:
                continue
            request_data = {
                'endpoint': f"""{self.jira_agile_url}/sprint/{sprint.id_on_jira}/issue?maxResults=200""",
                'method': 'get',
            }
            try:
                data = self.make_request(request_data, headers)
                for issue in data['issues']:
                    if issue['key'] in current_tickets:
                        current_tickets[issue['key']].sprint_id = sprint.id
                sprint.write({'updated': False})
            except Exception as e:
                _logger.warning(f"Loading issue of sprint {sprint.name} failed: " + str(e))
