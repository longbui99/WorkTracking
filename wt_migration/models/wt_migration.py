from email import header
from math import fabs
from threading import local
from turtle import end_poly
import requests
import json
import pytz
import logging
import base64
import time

from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.wt_migration.utils.ac_parsing import parsing, unparsing
from odoo.addons.wt_migration.models.mapping_table import IssueMapping, WorkLogMapping, ACMapping
from odoo.addons.base.models.res_partner import _tz_get
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TaskMigration(models.Model):
    _name = 'wt.migration'
    _description = 'Task Migration'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence')
    timezone = fields.Selection(_tz_get, string='Timezone', default="UTC", required=True)
    wt_server_url = fields.Char(string='Task Server URL')
    auth_type = fields.Selection([('basic', 'Basic'), ('api_token', 'API Token')], string="Authentication Type",
                                 default="basic")
    server_type = fields.Selection([('self_hosting', 'Self-Hosted'), ('cloud', 'Cloud')], string="Server Type",
                                   default="self_hosting")
    import_work_log = fields.Boolean(string='Import Work Logs?')
    auto_export_work_log = fields.Boolean(string="Auto Export Work Logs?")
    is_load_acs = fields.Boolean(string="Import Checklist?")
    wt_agile_url = fields.Char(string="Task Agile URL")
    admin_user_ids = fields.Many2many("res.users", string="Admins")
    active = fields.Boolean(string="Active?", default=True)

    def action_toggle(self):
        for record in self:
            record.active = not record.active

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
        employee_id = self._context.get('employee_id')
        if not employee_id:
            user = self.env.user or self.admin_user_ids
            employee_id = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
            if not employee_id:
                raise UserError(_("Don't have any related Employee, please set up on Employee Application"))
            if not employee_id.wt_private_key:
                raise UserError(_("Missing the Access token in the related Employee"))
            wt_private_key = employee_id.wt_private_key
        else:
            user = employee_id.user_id
            wt_private_key = employee_id.wt_private_key
        if self.auth_type == 'api_token':
            wt_private_key = "Basic " + base64.b64encode(
                f"{user.partner_id.email or user.login}:{wt_private_key}".encode('utf-8')).decode('utf-8')
        else:
            wt_private_key = "Bearer " + wt_private_key

        headers = {
            'Authorization': wt_private_key
        }
        return headers

    def _get_single_project(self, project_key):
        headers = self.__get_request_headers()
        result = requests.get(f"{self.wt_server_url}/project/{project_key}", headers=headers)
        record = json.loads(result.text)
        if self.env.context.get('employee_id'):
            user_id = self._context['employee_id'].user_id
        else:
            user_id = self.env['hr.employee'].search([('wt_private_key', '!=', False), ('user_id', '=', self.env.user.id)], limit=1).user_id
        res = {
            'project_name': record['name'],
            'project_key': record['key'],
            'wt_migration_id': self.id
        }
        if user_id:
            res['allowed_user_ids'] = [(4, user_id.id, False)]
        return self.env['wt.project'].sudo().create(res).id

    def _get_current_employee(self):
        return {
            "user_email": {user.partner_id.email or user.login for user in
                           self.with_context(active_test=False).env["res.users"].sudo().search([])}
        }

    def load_all_users(self, user_email=''):
        headers = self.__get_request_headers()
        current_employee_data = self._get_current_employee()
        result = requests.get(f'{self.wt_server_url}/user/search?startAt=0&maxResults=50000',
                              headers=headers)
        records = json.loads(result.text)
        if not isinstance(records, list):
            records = [records]
        users = self.env["res.users"].sudo()
        for record in records:
            if record["name"] not in current_employee_data["user_email"]:
                users |= self.env["res.users"].sudo().create({
                    "name": record["displayName"],
                    "login": record["name"],
                    'active': False
                })

    def load_projects(self):
        headers = self.__get_request_headers()
        # _logger.info(headers)
        result = requests.get(f"{self.wt_server_url}/project", headers=headers)
        existing_project = self.env['wt.project'].search([])
        existing_project_dict = {f"{r.project_key}": r for r in existing_project}
        user_id = False
        if self.env.context.get('employee_id'):
            user_id = self._context['employee_id'].user_id
        else:
            user_id = self.env['hr.employee'].search([('wt_private_key', '!=', False), ('user_id', '=', self.env.user.id)], limit=1).user_id
        new_project = []
        for record in json.loads(result.text):
            if not existing_project_dict.get(record.get('key', False), False):
                res = {
                    'project_name': record['name'],
                    'project_key': record['key'],
                    'wt_migration_id': self.id
                }
                if user_id:
                    res['allowed_user_ids'] = [(4, user_id.id, False)]
                new_project.append(res)
            else:
                project = existing_project_dict.get(record.get('key', False), False)
                if user_id:
                    project.sudo().allowed_user_ids = [(4, user_id.id, False)]

        if new_project:
            self.env['wt.project'].sudo().create(new_project)

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
        try:
            body = result.json()
        except Exception as e:
            _logger.error(e)
            _logger.warning(result.text)
        if isinstance(body, dict) and body.get('errorMessages', False):
            raise UserError("Task Server: \n" + "\n".join(body['errorMessages']))
        return body

    # ===========================================  Section for loading issues/issues =============================================
    @api.model
    def _create_new_acs(self, values=[], mapping=None):
        if not values:
            return []
        if not mapping:
            mapping = ACMapping(self.wt_server_url, self.server_type).parsing()
        if not isinstance(values, list):
            parsed_values = mapping(values)
        else:
            parsed_values = values
        return list(map(lambda r: (0, 0, {
            'name': parsing(r["name"]),
            'wt_raw_name': r["name"],
            "checked": r["checked"],
            "key": r["id"],
            "sequence": r["rank"],
            "is_header": r["isHeader"]
        }), parsed_values))

    def _update_acs(self, ac_ids, values=[], mapping=None):
        if not values:
            return False
        if not mapping:
            mapping = ACMapping(self.wt_server_url, self.server_type).parsing()
        parsed_values = mapping(values)
        value_keys = {r['id']: r for r in parsed_values}
        unexisting_records = ac_ids.filtered(lambda r: r.key not in value_keys)
        ac_ids -= unexisting_records
        unexisting_records.unlink()
        for record in ac_ids:
            r = value_keys[record.key]
            record.write({
                'name': parsing(r["name"]),
                'wt_raw_name': r["name"],
                "checked": r["checked"] or record.checked,
                "key": r["id"],
                "sequence": r["rank"],
                "is_header": r["isHeader"]
            })
            del value_keys[record.key]
        res = self._create_new_acs(list(value_keys.values()), mapping)
        return res

    def export_acceptance_criteria(self, issue_id):
        issue_mapping = IssueMapping(self.wt_server_url, self.server_type)
        ac_mapping = ACMapping(self.wt_server_url, self.server_type).exporting()
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/issue/{issue_id.issue_key}",
            'method': 'put',
        }
        updated_acs = ac_mapping(issue_id.ac_ids)
        payload = {
            "fields": {
                f"{issue_mapping.acceptance_criteria[0]}": updated_acs
            }
        }
        request_data['body'] = payload
        res = self.make_request(request_data, headers)
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
            'project_key_dict': {r.project_key: r.id for r in self.env['wt.project'].sudo().search([])},
            'dict_user': self.with_context(active_test=False).get_user(),
            'dict_issue_key': {r.issue_key: r for r in self.env['wt.issue'].sudo().search(domain)},
            'dict_status': {r.key: r.id for r in self.env['wt.status'].sudo().search([])},
            'dict_type': {r.key: r.id for r in self.env["wt.type"].sudo().search([])}
        }

    def mapping_issue(self, local, issue, issue_mapping, response,load_ac):
        issue_fields = issue['fields']
        status = self.__load_from_key_paths(issue_fields, issue_mapping.status)
        story_point = self.__load_from_key_paths(issue_fields, issue_mapping.story_point)
        estimate_hour = self.__load_from_key_paths(issue_fields, issue_mapping.estimate_hour) or 0.0
        assignee = self.__load_from_key_paths(issue_fields, issue_mapping.assignee)
        tester = self.__load_from_key_paths(issue_fields, issue_mapping.tester)
        project = self.__load_from_key_paths(issue_fields, issue_mapping.project)
        issue_type = self.__load_from_key_paths(issue_fields, issue_mapping.issue_type)
        summary = self.__load_from_key_paths(issue_fields, issue_mapping.summary)
        acceptance_criteria = self.__load_from_key_paths(issue_fields, issue_mapping.acceptance_criteria)
        created_date = self.__load_from_key_paths(issue_fields, issue_mapping.created_date)
        new_status = self.__load_from_key_paths(issue_fields, issue_mapping.new_status)
        wt_key = self.__load_from_key_paths(issue_fields, issue_mapping.wt_status)
        new_issue_type = self.__load_from_key_paths(issue_fields, issue_mapping.new_issue_key)
        if issue.get('key', '-') not in local['dict_issue_key']:
            if not issue_fields:
                return
            res = {
                'issue_name': summary,
                'issue_key': issue['key'],
                'issue_url': issue_mapping.map_url(issue['key']),
                'story_point': estimate_hour and estimate_hour or story_point,
                'wt_migration_id': self.id,
                'create_date': created_date,
                'wt_id': issue['id']
            }
            if issue_fields.get('parent'):
                if issue_fields['parent']['key'] not in local['dict_issue_key']:
                    issue_fields['parent']['fields']['project'] = issue_fields['project']
                    epic = []
                    self.mapping_issue(local, issue_fields['parent'], issue_mapping, epic, load_ac)
<<<<<<< HEAD
                    local['dict_issue_key'][issue_fields['parent']['key']] = self.env["wt.issue"].sudo().create(epic)
=======
                    local['dict_issue_key'][issue_fields['parent']['key']] = self.env["wt.issue"].sudo().with_context(
                        default_epic_ok=True).create(epic)
>>>>>>> 525be0b2b47fe1df2e783d8b8674f93d5de1078b
                res['epic_id'] = local['dict_issue_key'][issue_fields['parent']['key']].id
            if estimate_hour:
                res['story_point_unit'] = 'hrs'
            if local['project_key_dict'].get(project, False):
                res['project_id'] = local['project_key_dict'][project]
            else:
                local['project_key_dict'][project] = self.sudo()._get_single_project(project)
                res['project_id'] = local['project_key_dict'][project]
            if local['dict_user'].get(assignee, False):
                res['assignee_id'] = local['dict_user'][assignee]
            elif assignee:
                new_user = self.env['res.users'].sudo().create({
                    'name': self.__load_from_key_paths(issue_fields, issue_mapping.assignee_name),
                    'login': assignee,
                    'active': False
                })
                res['assignee_id'] = new_user.id
                local['dict_user'][assignee] = new_user.id
            if local['dict_user'].get(tester, False):
                res['tester_id'] = local['dict_user'][tester]
            elif tester:
                new_user = self.env['res.users'].sudo().create({
                    'name': self.__load_from_key_paths(issue_fields, issue_mapping.tester_name),
                    'login': tester,
                    'active': False
                })
                res['tester_id'] = new_user.id
                local['dict_user'][tester] = new_user.id
            if local['dict_status'].get(status, False):
                res['status_id'] = local['dict_status'][status]
            else:
                status_id = self.env['wt.status'].sudo().create({
                    'name': new_status['name'],
                    'key': new_status['id'],
                    'wt_key': wt_key
                }).id
                local['dict_status'][status] = status_id
                res['status_id'] = local['dict_status'][status]
            if local["dict_type"].get(issue_type, False):
                res['issue_type_id'] = local['dict_type'][issue_type]
            else:
                new_issue_type_id = self.env['wt.type'].sudo().create({
                    'name': new_issue_type['name'],
                    'img_url': new_issue_type['iconUrl'],
                    'key': issue_type
                }).id
                local['dict_type'][issue_type] = new_issue_type_id
                res['issue_type_id'] = local['dict_type'][issue_type]
            if load_ac:
                res["ac_ids"] = self._create_new_acs(acceptance_criteria)
            response.append(res)
        else:
            existing_record = local['dict_issue_key'][issue.get('key', '-')]
            update_dict = {
                'story_point': estimate_hour and estimate_hour or story_point,
            }
            if issue_fields.get('parent'):
                if issue_fields['parent']['key'] != existing_record.epic_id.issue_key:
                    if issue_fields['parent']['key'] not in local['dict_issue_key']:
                        issue_fields['parent']['fields']['project'] = issue_fields['project']
                        epic = []
                        self.mapping_issue(local, issue_fields['parent'], issue_mapping, epic, load_ac)
                        local['dict_issue_key'][issue_fields['parent']['key']] = self.env["wt.issue"].sudo().with_context(
                            default_epic_ok=True).create(epic)
                    update_dict['epic_id'] = local['dict_issue_key'][issue_fields['parent']['key']].id
            if estimate_hour:
                update_dict['story_point_unit'] = 'hrs'
            if existing_record.issue_name != summary:
                update_dict['issue_name'] = summary
            if existing_record.status_id.id != local['dict_status'].get(status):
                if status not in local['dict_status']:
                    status_id = self.env['wt.status'].sudo().create({
                        'name': new_status['name'],
                        'key': new_status['id'],
                        'wt_key': wt_key
                    }).id
                    local['dict_status'][status] = status_id
                update_dict['status_id'] = local['dict_status'][status]
            if existing_record.issue_type_id.id != local['dict_type'].get(issue_type):
                update_dict['issue_type_id'] = local['dict_type'][issue_type]
            if assignee and assignee in local['dict_user'] and existing_record.assignee_id.id != local['dict_user'][
                assignee]:
                update_dict['assignee_id'] = local['dict_user'][assignee]
            if tester and tester in local['dict_user'] and existing_record.tester_id.id != local['dict_user'][
                tester]:
                update_dict['tester_id'] = local['dict_user'][tester]
            if load_ac:
                res = self._update_acs(existing_record.ac_ids, acceptance_criteria)
                if res:
                    update_dict['ac_ids'] = res
            existing_record.write(update_dict)

            if response and not isinstance(response[0], dict):
                response[0] |= existing_record
            else:
                response.insert(0, existing_record)

    def processing_issue_raw_data(self, local, raw):
        issue_mapping = IssueMapping(self.wt_server_url, self.server_type)
        response = []
        load_ac = self.is_load_acs
        for issue in raw.get('issues', [raw]):
            self.mapping_issue(local, issue, issue_mapping, response, load_ac)
        return response

    def do_request(self, request_data, domain=[], paging=100, load_all=False):
        existing_record = self.env['wt.issue']
        headers = self.__get_request_headers()
        # _logger.info(headers)
        start_index = 0
        total_response = paging
        response = []
        local_data = self.get_local_issue_data(domain)
        request_data['params'] = request_data.get('params', [])
        request = request_data.copy()
        failed_count = 0
        while start_index < total_response and failed_count < 6:
            page_size = paging if total_response - start_index > paging else total_response - start_index
            params = request_data['params'].copy()
            params += [f'startAt={start_index}']
            params += [f'maxResults={page_size}']
            request['params'] = params
            body = self.make_request(request, headers)
            if not isinstance(body, dict):
                failed_count += 1
                time.sleep(30)
                continue
            failed_count = 0
            if body.get('total', 0) > total_response and load_all:
                total_response = body['total']
            start_index += paging
            new_issues = self.processing_issue_raw_data(local_data, body)
            if new_issues:
                if not isinstance(new_issues[0], dict):
                    existing_record |= new_issues[0]
                    new_issues.pop(0)
            response.extend(new_issues)
        print(json.dumps(response, indent=4))
        return existing_record | self.env['wt.issue'].sudo().create(response)

    def load_issues(self, extra_jql="", domain=[], load_all=False):
        request_data = {
            'endpoint': f"{self.wt_server_url}/search",
            'params': [extra_jql]
        }
        return self.do_request(request_data, domain=domain, load_all=load_all)

    def load_all_issues(self):
        issue_ids = self.load_issues(load_all=True)
        if issue_ids and self.import_work_log:
            for issue_id in issue_ids:
                self.with_delay().load_work_logs(issue_id)

    def load_my_issues(self):
        extra_jql = f"""jql=assignee='{self.env.user.partner_id.email}' ORDER BY createdDate ASC"""
        issue_ids = self.load_issues(extra_jql, domain=[('assignee_id', '=', self.env.user.id)], load_all=True)
        if issue_ids and self.import_work_log:
            for issue_id in issue_ids:
                self.with_delay().load_work_logs(issue_id)

    def load_by_links(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("wt_migration.load_by_link_action_form")
        context = json.loads(action['context'])
        context.update({'default_migration_id': self.id})
        action['context'] = context
        return action

    @api.model
    def search_issue(self, keyword):
        return self.search_load(keyword)

    def _search_load(self, res, delay=False):
        issue_ids = self.env['wt.issue']
        if 'issue' in res:
            if not isinstance(res['issue'], (list, tuple)):
                res['issue'] = [res['issue']]
            for key in res['issue']:
                request_data = {
                    'endpoint': f"{self.wt_server_url}/issue/{key.upper()}",
                }
                issue_ids |= self.do_request(request_data,
                                             ['|', ('issue_key', 'in', res['issue']), ('epic_ok', '=', True)])
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
                'endpoint': f"{self.wt_server_url}/search",
                "params": [query]
            }
            issue_ids |= self.do_request(request_data, load_all=True)
        if delay:
            self.with_delay().load_work_logs(issue_ids)
        else:
            self.load_work_logs(issue_ids)

        return issue_ids

    def search_load(self, payload):
        res = get_search_request(payload)
        return self._search_load(res)

    # ===========================================  Section for loading work logs ===================================
    def get_user(self):
        return {r.partner_id.email or r.login: r.id for r in self.env['res.users'].sudo().search([])}

    def get_local_worklog_data(self, issue_id, domain):
        return {
            'work_logs': {x.id_on_wt: x for x in issue_id.time_log_ids if x.id_on_wt},
            'issues': {issue_id.wt_id: issue_id.id},
            'issue_to_logs': {}
        }

    def update_work_log_data(self, log_id, work_log, data, mapping):
        to_update = {}
        work_log_id = data['work_logs'][log_id]
        if work_log_id.duration != work_log['timeSpentSeconds']:
            to_update['duration'] = work_log['timeSpentSeconds']
            to_update['time'] = work_log['timeSpent']
        logging_email = self.__load_from_key_paths(work_log, mapping.author)
        start_date = self.convert_server_tz_to_utc(self.__load_from_key_paths(work_log, mapping.start_date))
        if work_log_id.user_id.id != data['dict_user'].get(logging_email, False):
            to_update['user_id'] = data['dict_user'].get(logging_email, False)
        if not work_log_id.start_date or work_log_id.start_date.isoformat()[:16] != start_date.isoformat()[:16]:
            to_update['start_date'] = start_date
        if to_update:
            work_log_id.write(to_update)

    def processing_worklog_raw_data(self, data, body, mapping=False):
        if not mapping:
            mapping = WorkLogMapping(self.wt_server_url, self.server_type)
        new_issues = []
        issues = data['issues']
        affected_wt_ids = set()
        for work_log in body.get('worklogs', [body]):
            log_id = int(work_log.get('id', '-'))
            affected_wt_ids.add(log_id)
            time = self.__load_from_key_paths(work_log, mapping.time)
            duration = self.__load_from_key_paths(work_log, mapping.duration)
            description = self.__load_from_key_paths(work_log, mapping.description) or ''
            id_on_wt = self.__load_from_key_paths(work_log, mapping.id_on_wt)
            start_date = self.__load_from_key_paths(work_log, mapping.start_date)
            logging_email = self.__load_from_key_paths(work_log, mapping.author)
            if log_id not in data['work_logs']:
                if duration > 0 and issues.get(int(work_log['issueId']), False):
                    to_create = {
                        'time': time,
                        'duration': duration,
                        'description': description,
                        'state': 'done',
                        'source': 'sync',
                        'issue_id': issues.get(int(work_log['issueId']), False),
                        'id_on_wt': id_on_wt,
                        'start_date': self.convert_server_tz_to_utc(start_date),
                        'user_id': data['dict_user'].get(logging_email, False),
                        'is_exported': True
                    }
                    new_issues.append(to_create)
            else:
                self.update_work_log_data(log_id, work_log, data, mapping)
        if self.env.context.get('force_delete', False):
            deleted = set(list(data['work_logs'].keys())) - affected_wt_ids
            if deleted:
                self.env['wt.time.log'].search([('id_on_wt', 'in', list(deleted))]).unlink()

        return new_issues

    def load_work_logs_by_unix(self, unix, employee_ids, batch=900):
        if self.import_work_log:
            for employee_id in employee_ids:
                self = self.with_context(employee_id=employee_id)
                unix = int(self.env['ir.config_parameter'].get_param('latest_unix'))
                last_page = False
                mapping = WorkLogMapping(self.wt_server_url, self.server_type)
                headers = self.__get_request_headers()
                issue_ids = self.env['wt.issue'].search(
                    [('wt_id', '!=', False), ('write_date', '>=', datetime.fromtimestamp(unix / 1000))])
                local_data = {
                    'work_logs': {x.id_on_wt: x for x in issue_ids.mapped('time_log_ids') if x.id_on_wt},
                    'issues': {issue_id.wt_id: issue_id.id for issue_id in issue_ids},
                    'dict_user': self.with_context(active_test=False).get_user()
                }
                flush = []
                to_create = []
                request_data = {
                    'endpoint': f"{self.wt_server_url}/worklog/updated?since={unix}",
                }
                page_failed_count = 0
                while not last_page and page_failed_count < 6:
                    body = self.make_request(request_data, headers)
                    if isinstance(body, dict):
                        page_failed_count = 0
                        request_data['endpoint'] = body.get('nextPage', '')
                        last_page = body.get('lastPage', True)
                        ids = list(map(lambda r: r['worklogId'], body.get('values', [])))
                        flush.extend(ids)
                        log_failed_count = 0
                        while log_failed_count < 6:
                            if len(flush) > batch or last_page:
                                request = {
                                    'endpoint': f"{self.wt_server_url}/worklog/list",
                                    'method': 'post',
                                    'body': {'ids': flush}
                                }
                                logs = self.make_request(request, headers)
                                if isinstance(logs, list):
                                    log_failed_count = 0
                                    data = {'worklogs': logs}
                                    new_logs = self.processing_worklog_raw_data(local_data, data, mapping)
                                    to_create.extend(new_logs)
                                    flush = []
                                    break
                                else:
                                    _logger.warning(f"WORK LOG LOAD FAILED COUNT: {log_failed_count}")
                                    log_failed_count += 1
                                    time.sleep(30)
                                    continue
                        del body['values']
                        _logger.info(json.dumps(body, indent=4))
                    else:
                        _logger.warning(f"PAGE LOAD FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue
                if len(to_create):
                    self.env["wt.time.log"].create(to_create)
            self.env['ir.config_parameter'].set_param('latest_unix',
                                                    body.get('until', datetime.now().timestamp() * 1000))

    def delete_work_logs_by_unix(self, unix, employee_ids, batch=900):
        if self.import_work_log:
            for employee_id in employee_ids:
                self = self.with_context(employee_id=employee_id)
                unix = int(self.env['ir.config_parameter'].get_param('latest_unix'))
                last_page = False
                headers = self.__get_request_headers()
                flush = []
                request_data = {
                    'endpoint': f"{self.wt_server_url}/worklog/deleted?since={unix}",
                }
                page_failed_count = 0
                while not last_page and page_failed_count < 6:
                    body = self.make_request(request_data, headers)
                    if isinstance(body, dict):
                        page_failed_count = 0
                        request_data['endpoint'] = body.get('nextPage', '')
                        last_page = body.get('lastPage', True)
                        ids = list(map(lambda r: r['worklogId'], body.get('values', [])))
                        flush.extend(ids)
                        if len(flush) > batch or last_page:
                            self.env['wt.time.log'].search([('id_on_wt', 'in', flush)]).unlink()
                            flush = []
                        del body['values']
                        _logger.info(json.dumps(body, indent=4))
                    else:
                        _logger.warning(f"PAGE DELETED FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue

    def load_work_logs(self, issue_ids, paging=100, domain=[], load_all=False):
        if self.import_work_log:
            mapping = WorkLogMapping(self.wt_server_url, self.server_type)
            headers = self.__get_request_headers()
            user_dict = self.with_context(active_test=False).get_user()
            for issue_id in issue_ids:
                request_data = {
                    'endpoint': f"{self.wt_server_url}/issue/{issue_id.issue_key}/worklog",
                }
                start_index = 0
                total_response = paging
                to_create = []
                local_data = self.get_local_worklog_data(issue_id, domain)
                local_data['dict_user'] = user_dict
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
                    new_issues = self.with_context(force_delete=True).processing_worklog_raw_data(local_data, body, mapping)
                    to_create.extend(new_issues)
                if to_create:
                    self.env['wt.time.log'].create(to_create)

    @api.model
    def _get_time_log_payload(self, time_log_id):
        return {
            "comment": time_log_id.description,
            "started": time_log_id.start_date.isoformat(sep='T', timespec='milliseconds') + "+0000",
            "timeSpentSeconds": time_log_id.duration
        }

    def add_time_logs(self, issue_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/issue/{issue_id.issue_key}/worklog",
            'method': 'post',
        }
        for log in time_log_ids:
            payload = self._get_time_log_payload(log)
            request_data['body'] = payload
            res = self.make_request(request_data, headers)
            log.id_on_wt = res['id']
        time_log_ids.is_exported = True

    def update_time_logs(self, issue_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/issue/{issue_id.issue_key}/worklog",
            'method': 'put',
        }
        for log in time_log_ids:
            try:
                payload = self._get_time_log_payload(log)
                request_data['body'] = payload
                request_clone = request_data.copy()
                request_clone['endpoint'] += f"/{log.id_on_wt}"
                res = self.make_request(request_clone, headers)
            except:
                continue
        time_log_ids.is_exported = True

    def delete_time_logs(self, issue_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/issue/{issue_id.issue_key}/worklog",
            'method': 'delete',
        }
        for log in time_log_ids:
            payload = self._get_time_log_payload(log)
            request_data['body'] = payload
            request_clone = request_data.copy()
            request_clone['endpoint'] += f"/{log.id_on_wt}"
            res = self.make_request(request_clone, headers)
            
    def export_specific_log(self, issue_id, log_ids):
        time_log_to_create_ids = log_ids.filtered(lambda x: not x.id_on_wt and x.state == 'done')
        time_log_to_update_ids = log_ids.filtered(lambda x: x.id_on_wt and x.state == 'done')
        self.add_time_logs(issue_id, time_log_to_create_ids)
        self.update_time_logs(issue_id, time_log_to_update_ids)

    def export_time_log(self, issue_id):
        current_user_id = self.env.user.id
        time_log_to_create_ids = issue_id.time_log_ids.filtered(lambda x: not x.id_on_wt and x.state == 'done')
        time_log_to_update_ids = issue_id.time_log_ids.filtered(
            lambda x: x.id_on_wt
                      and (not issue_id.last_export or x.write_date > issue_id.last_export)
                      and (x.user_id.id == current_user_id)
                      and x.state == 'done'
        )
        self.add_time_logs(issue_id, time_log_to_create_ids)
        self.update_time_logs(issue_id, time_log_to_update_ids)

    def _update_project(self, project_id, employee_id):
        self = self.with_context(employee_id=employee_id)
        updated_date = datetime(1970, 1, 1, 1, 1, 1, 1)
        if project_id.last_update:
            updated_date = self.convert_utc_to_usertz(project_id.last_update)
        str_updated_date = updated_date.strftime('%Y-%m-%d %H:%M')
        params = f"""jql=project="{project_id.project_key}" AND updated >= '{str_updated_date}'"""
        request_data = {'endpoint': f"{self.wt_server_url}/search", "params": [params]}
        issue_ids = self.do_request(request_data, load_all=True)
        # _logger.info(f"=====================================================================")
        _logger.info(f"{project_id.project_name}: {len(issue_ids)}")
        # _logger.info(f"_____________________________________________________________________")
        project_id.last_update = datetime.now()

    def update_project(self, project_id, access_token):
        self.with_delay()._update_project(project_id, access_token)

    def update_boards(self):
        project_ids = self.env["wt.project"].search([])
        self.load_boards(project_ids=project_ids)
        for project_id in project_ids:
            self.with_delay().update_board(project_id)

    def update_board(self, project_id):
        # _logger.info(f"+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        # _logger.info(f"Load Work Log")
        self.load_sprints(project_id.board_ids)
        # _logger.info(f"Load Sprint")
        self.with_context(force=True).update_issue_for_sprints(project_id.sprint_ids)
        # _logger.info(f"+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")

    # Agile Connection
    def load_boards(self, project_ids=False):
        if not self.wt_agile_url:
            return
        if not project_ids:
            project_ids = self.env["wt.project"].search([])
        headers = self.__get_request_headers()
        for project in project_ids:
            request_data = {
                'endpoint': f"""{self.wt_agile_url}/board?projectKeyOrId={project.project_key}""",
                'method': 'get',
            }
            current_boards = set(project.board_ids.mapped('id_on_wt'))
            try:
                data = self.make_request(request_data, headers)
                for board in data['values']:
                    if board['id'] not in current_boards:
                        self.env["board.board"].sudo().create({
                            'id_on_wt': board['id'],
                            'name': board['name'],
                            'type': board['type'],
                            'project_id': project.id
                        })
            except Exception as e:
                _logger.warning(f"Loading board on project {project.project_name} failed: " + str(e))

    def load_sprints(self, board_ids=False):
        if not self.wt_agile_url:
            return
        if not board_ids:
            board_ids = self.env['board.board'].search([])
        board_ids = board_ids.filtered(lambda r: r.type == "scrum")
        headers = self.__get_request_headers()
        for board in board_ids:
            if not board.id_on_wt and not board.type == 'scrum':
                continue
            request_data = {
                'endpoint': f"""{self.wt_agile_url}/board/{board.id_on_wt}/sprint?maxResults=2000""",
                'method': 'get',
            }
            current_sprints = {x.id_on_wt: x for x in board.sprint_ids}
            try:
                data = self.make_request(request_data, headers)
                for sprint in data['values']:
                    if sprint['id'] not in current_sprints:
                        self.env["agile.sprint"].sudo().create({
                            'id_on_wt': sprint['id'],
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
        current_issues = {x.issue_key: x for x in self.env["wt.issue"].search(
            [('create_date', '>', datetime.now() - relativedelta(months=2))])}
        force = self.env.context.get('force', False)
        for sprint in sprint_ids:
            if not sprint.id_on_wt:
                continue
            request_data = {
                'endpoint': f"""{self.wt_agile_url}/sprint/{sprint.id_on_wt}/issue?maxResults=200&fields=""""",
                'method': 'get',
            }
            try:
                data = self.make_request(request_data, headers)
                for issue in data['issues']:
                    if issue['key'] in current_issues:
                        current_issues[issue['key']].sprint_id = sprint.id
                sprint.write({'updated': False})
            except Exception as e:
                _logger.warning(f"Loading issue of sprint {sprint.name} failed: " + str(e))
