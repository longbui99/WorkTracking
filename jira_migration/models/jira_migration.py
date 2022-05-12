import requests
import json
from dateutil import parser

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
    def __load_from_key_paths(self, object, paths):
        res = object
        for key in paths:
            if key in res and res.get(key) is not None:
                res = res[key]
            else:
                return None
        return res

    @api.model
    def make_request(self, request_data, headers):
        endpoint = request_data.get('endpoint', None)
        if not endpoint:
            return {}
        if 'params' in request_data:
            endpoint += "?" + '&'.join(request_data['params'])
        result = requests.get(endpoint, headers=headers)
        body = json.loads(result.text)
        return body

    def get_local_data(self, domain=[]):
        return {
            'project_key_dict': {r.project_key: r.id for r in self.env['jira.project'].sudo().search([])},
            'dict_user': {r.login: r.id for r in self.env['res.users'].sudo().search([])},
            'dict_ticket_key': {r.ticket_key: r for r in self.env['jira.ticket'].sudo().search(domain)},
            'dict_status': {r.key: r.id for r in self.env['jira.status'].sudo().search([])},
        }

    def processing_issue_raw_data(self, local, raw):
        new_tickets = []
        if raw.get('errorMessages', False):
            raise UserError(_("\n".join(raw['errorMessages'])))
        for ticket in raw.get('issues', [raw]):
            if ticket.get('key', '-') not in local['dict_ticket_key']:
                ticket_fields = ticket['fields']
                if not ticket_fields:
                    continue
                res = {
                    'ticket_name': ticket_fields['summary'],
                    'ticket_key': ticket['key'],
                    'ticket_url': ticket['self'],
                    'story_point': ticket_fields.get('customfield_10008', 0.0) or 0.0,
                    'jira_migration_id': self.id
                }
                project = self.__load_from_key_paths(ticket_fields, ['project', 'key'])
                if local['project_key_dict'].get(project, False):
                    res['project_id'] = local['project_key_dict'][project]
                assignee = self.__load_from_key_paths(ticket_fields, ['assignee', 'key'])
                if local['dict_user'].get(assignee, False):
                    res['assignee_id'] = local['dict_user'][assignee]
                status = self.__load_from_key_paths(ticket_fields, ['status', 'id'])
                if local['dict_status'].get(status, False):
                    res['status_id'] = local['dict_status'][status]
                else:
                    new_status = self.__load_from_key_paths(ticket_fields, ['status', 'id'])
                    status_id = self.env['jira.status'].create({
                        'name': new_status['name'],
                        'key': new_status['id'],
                    }).id
                    local['dict_status'][status] = status_id
                work_log = self.__load_from_key_paths(ticket_fields, ['progress', 'progress'])
                if ticket_fields['progress']['progress'] > 0:
                    res['time_log_ids'] = [fields.Command.create(
                        {
                            'name': 'Time Log',
                            'time': 'char',
                            'description': 'No Comment',
                            'duration': work_log
                        }
                    )]
                new_tickets.append(res)
        return new_tickets

    def do_request(self, request_data, domain=[], paging=50, load_all=False):
        headers = self.__get_request_headers()
        start_index = 0
        total_response = paging
        to_create_tickets = []
        local_data = self.get_local_data(domain)
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
            to_create_tickets.extend(new_tickets)
        if to_create_tickets:
            self.env['jira.ticket'].create(to_create_tickets)

    def load_tickets(self, extra_jql="", domain=[], load_all=False):
        request_data = {
            'endpoint': f"{self.jira_server_url}/search",
            'params': [extra_jql]
        }
        self.do_request(request_data, domain=domain, load_all=load_all)

    def load_all_tickets(self):
        self.load_tickets(load_all=True)

    def load_my_tickets(self):
        extra_jql = f"""jql=assignee='{self.env.user.login}' ORDER BY createdDate ASC"""
        self.load_tickets(extra_jql, domain=[('assignee_id', '=', self.env.user.id)], load_all=True)

    def load_by_links(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("jira_migration.load_by_link_action_form")
        context = json.loads(action['context'])
        context.update({'default_migration_id': self.id})
        action['context'] = context
        return action

    def load_by_keys(self, type, keys):
        if type == 'ticket':
            for key in keys:
                request_data = {
                    'endpoint': f"{self.jira_server_url}/issue/{key}",
                }
                self.do_request(request_data, [('ticket_key', 'in', keys)])
        elif type == 'project':
            request_data = {
                'endpoint': f"{self.jira_server_url}/search",
                "params": [
                    f"""jql={' OR '.join(list(map(lambda x: f'project="{x}"', keys)))} ORDER BY createdDate ASC"""
                ]
            }
            self.do_request(request_data, load_all=True)

    def process_log_time_to_ticket(self, ticket_id):
        pass
