import requests
import json
import pytz
import logging
import base64
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.wt_migration.utils.ac_parsing import parsing, unparsing
from odoo.addons.wt_migration.models.mapping_table import IssueMapping, WorkLogMapping, ACMapping
from odoo.addons.wt_sdk.jira.import_jira_formatter import ImportingJiraIssue, ImportingJiraWorkLog
from odoo.addons.base.models.res_partner import _tz_get

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SPECIAL_FIELDS = {'write_date', 'create_date', 'write_uid', 'create_uid'}


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
            user_id = self.env['hr.employee'].search(
                [('wt_private_key', '!=', False), ('user_id', '=', self.env.user.id)], limit=1).user_id
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
        result = requests.get(f"{self.wt_server_url}/project", headers=headers)
        existing_project = self.env['wt.project'].search([])
        existing_project_dict = {f"{r.project_key}": r for r in existing_project}
        user_id = False
        if self.env.context.get('employee_id'):
            user_id = self._context['employee_id'].user_id
        else:
            user_id = self.env['hr.employee'].search(
                [('wt_private_key', '!=', False), ('user_id', '=', self.env.user.id)], limit=1).user_id
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
            return body
        except Exception as e:
            _logger.error(e)
            _logger.warning(result.text)
        if isinstance(body, dict) and body.get('errorMessages', False):
            raise UserError("Task Server: \n" + "\n".join(body['errorMessages']))

    def get_user(self):
        return {r.partner_id.email or r.login: r.id for r in self.env['res.users'].sudo().search([])}

    @api.model
    def minify_with_existing_record(self, curd_data, existing_record):
        index, length, keys = 0, len(curd_data.keys()), list(curd_data.keys())
        while index < length:
            if keys[index] not in SPECIAL_FIELDS:
                value = getattr(existing_record, keys[index])
                _logger.info(value)
                if isinstance(value, models.Model):
                    if value.id == curd_data[keys[index]]:
                        del curd_data[keys[index]]
                elif isinstance(value, datetime):
                    if value and value.isoformat()[:16] == curd_data[keys[index]].isoformat()[:16]:
                        del curd_data[keys[index]]
                elif isinstance(value, str):
                    if value == curd_data[keys[index]]:
                        del curd_data[keys[index]]
                elif float(value) == float(curd_data[keys[index]]):
                    del curd_data[keys[index]]
            else:
                del curd_data[keys[index]]
            index += 1
        return curd_data

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

    def get_local_issue_data(self, domain=[]):
        return {
            'dict_project_key': {r.project_key: r.id for r in self.env['wt.project'].sudo().search([])},
            'dict_user': self.with_context(active_test=False).get_user(),
            'dict_issue_key': {r.issue_key: r for r in self.env['wt.issue'].sudo().search(domain)},
            'dict_status': {r.key: r.id for r in self.env['wt.status'].sudo().search([])},
            'dict_type': {r.key: r.id for r in self.env["wt.type"].sudo().search([])}
        }

    def mapping_issue(self, local, issue, response):
        curd_data = {
            'issue_name': issue.summary,
            'issue_key': issue.issue_key,
            'issue_url': issue.issue_url,
            'story_point': issue.hour_point and issue.hour_point or issue.fibonacci_point,
            'story_point_unit': issue.hour_point and 'hrs' or 'general',
            'wt_migration_id': self.id,
            'wt_id': issue.remote_id
        }
        if issue.epic:
            curd_data['epic_id'] = local['dict_issue_key'].get(issue.epic.issue_key)
        curd_data['project_id'] = local['dict_project_key'].get(issue.project_key)
        curd_data['assignee_id'] = local['dict_user'].get(issue.assignee_email)
        curd_data['tester_id'] = local['dict_user'].get(issue.tester_email)
        curd_data['status_id'] = local['dict_status'].get(issue.status_key)
        curd_data['issue_type_id'] = local['dict_type'].get(issue.issue_type_key)
        index, length, keys = 0, len(curd_data.keys()), list(curd_data.keys())
        while index < length:
            if curd_data[keys[index]] is None:
                del curd_data[keys[index]]
            index += 1
        if issue.issue_key not in local['dict_issue_key']:
            response['new'].append(curd_data)
        else:
            existing_issue = local['dict_issue_key'].get(issue.issue_key)
            curd_data = self.minify_with_existing_record(curd_data, existing_issue)
            response['updated'] |= existing_issue
            if len(curd_data.keys()):
                existing_issue.write(curd_data)

    def create_missing_projects(self, issues, local):
        to_create_projects = [issue.project_key for issue in issues if issue.project_key not in local['dict_project_key']]
        if len(to_create_projects):
            for project in to_create_projects:
                local['dict_project_key'][project] = self._get_single_project(project_key=project)

    def create_missing_users(self, issues, local):
        to_create_users = [(issue.assignee_email, issue.assignee_name) for issue in issues if
                           issue.assignee_email and issue.assignee_email not in local['dict_user']]
        to_create_users += [(issue.tester_email, issue.tester_name) for issue in issues if
                            issue.tester_email and issue.tester_email not in local['dict_user']]
        for user in to_create_users:
            local['dict_user'][user[0]] = self.env['res.users'].sudo().create({
                'login': user[0],
                'name': user[1],
                'active': False
            }).id

    def create_missing_statuses(self, issues, local):
        for issue in issues:
            if issue.remote_status_id not in local['dict_status']:
                local['dict_status'][issue.remote_status_id] = self.env['wt.status'].sudo().create({
                    'name': issue.raw_status_key['name'],
                    'key': issue.status_key,
                    'wt_key': issue.remote_status_id
                }).id

    def create_missing_types(self, issues, local):
        for issue in issues:
            if issue.issue_type_key not in local['dict_type']:
                local['dict_type'][issue.issue_type_key] = self.env['wt.type'].sudo().create({
                    'name': issue.raw_type['name'],
                    'img_url': issue.raw_type['iconUrl'],
                    'key': issue.issue_type_key
                }).id

    def create_missing_epics(self, issues, local):
        for issue in issues:
            if issue.epic and issue.epic.issue_key not in local['dict_issue_key']:
                epics = {'new': []}
                self.mapping_issue(local, issue.epic, epics)
                res = self.env['wt.issue'].sudo().with_context(default_epic_ok=True).create(epics['new'])
                local['dict_issue_key'][res.issue_key] = res

    def processing_issue_raw_data(self, local, raw):
        importing_base = ImportingJiraIssue(self.server_type, self.wt_server_url)
        response = {
            'new': [],
            'updated': self.env['wt.issue']
        }
        raw_issues = raw.get('issues', [raw])
        issues = importing_base.parse_issues(raw_issues)
        self.create_missing_projects(issues, local)
        self.create_missing_users(issues, local)
        self.create_missing_statuses(issues, local)
        self.create_missing_types(issues, local)
        self.create_missing_epics(issues, local)
        for issue in issues:
            self.mapping_issue(local, issue, response)
        return response

    def do_request(self, request_data, domain=[], paging=100, load_all=False):
        existing_record = self.env['wt.issue']
        headers = self.__get_request_headers()
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
            res = self.processing_issue_raw_data(local_data, body)
            if res:
                existing_record |= res['updated']
            response.extend(res['new'])
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

    def get_local_worklog_data(self, issue_id, domain):
        return {
            'dict_log': {x.id_on_wt: x for x in issue_id.time_log_ids if x.id_on_wt},
            'dict_issue': {issue_id.wt_id: issue_id.id},
            'dict_issue_to_log': {}
        }

    def mapping_worklog(self, local, log, issue, response):
        curd_data = {
            'time': log.time,
            'duration': log.duration,
            'description': log.description,
            'id_on_wt': log.remote_id,
            'start_date': self.convert_server_tz_to_utc(log.start_date),
            'user_id': local['dict_user'][log.author],
            'state': 'done',
            'source': 'sync',
            'issue_id': issue.get(int(log.remote_issue_id), False),
            'is_exported': True
        }
        if log.remote_id not in local['dict_log']:
            if log.duration > 0 and issue.get(int(log.remote_issue_id), False):
                response['new'].append(curd_data)
        else:
            existing_log = local['dict_log'].get(log.remote_id)
            curd_data = self.minify_with_existing_record(curd_data, existing_log)
            if len(curd_data.keys()):
                existing_log.write(curd_data)
                response['updated'] |= existing_log

    def processing_worklog_raw_data(self, local, raw, mapping):
        if not mapping:
            mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
        response = {
            'new': [],
            'updated': self.env['wt.time.log']
        }
        raw_logs = raw.get('worklogs', [raw])
        logs = mapping.parse_logs(raw_logs)
        issue = local['dict_issue']
        for log in logs:
            self.mapping_worklog(local, log, issue, response)
        return response

    def load_work_logs_by_unix(self, unix, employee_ids, batch=900):
        if self.import_work_log:
            for employee_id in employee_ids:
                self = self.with_context(employee_id=employee_id)
                last_page = False
                mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
                headers = self.__get_request_headers()
                issue_ids = self.env['wt.issue'].search(
                    [('wt_id', '!=', False), ('write_date', '>=', datetime.fromtimestamp(unix / 1000))])
                local_data = {
                    'dict_log': {x.id_on_wt: x for x in issue_ids.mapped('time_log_ids') if x.id_on_wt},
                    'dict_issue': {issue_id.wt_id: issue_id.id for issue_id in issue_ids},
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
                                    to_create.extend(new_logs.get('new'))
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

    def delete_work_logs_by_unix(self, unix, employee_ids, batch=900):
        if self.import_work_log:
            for employee_id in employee_ids:
                self = self.with_context(employee_id=employee_id)
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
            mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
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
                    new_issues = self.with_context(force_delete=True).processing_worklog_raw_data(local_data, body,
                                                                                                  mapping)
                    to_create.extend(new_issues.get('new'))
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
        _logger.info(f"{project_id.project_name}: {len(issue_ids)}")

    def update_project(self, project_id, access_token):
        self.with_delay()._update_project(project_id, access_token)
    
    def update_projects(self, latest_unix, employee_ids):
        for employee_id in employee_ids:
            self = self.with_context(employee_id=employee_id)
            str_updated_date = self.convert_utc_to_usertz(datetime.fromtimestamp(latest_unix/1000)).strftime('%Y-%m-%d %H:%M')
            params = f"""jql=updated >= '{str_updated_date}'"""
            request_data = {'endpoint': f"{self.wt_server_url}/search", "params": [params]}
            issue_ids = self.do_request(request_data, load_all=True)
            _logger.info(f"Batch Load Of User {employee_id.name}: {len(issue_ids)}")
            _logger.info(",".join(issue_ids.mapped('issue_key')))

    def update_boards(self):
        project_ids = self.env["wt.project"].search([])
        self.load_boards(project_ids=project_ids)
        for project_id in project_ids:
            self.with_delay().update_board(project_id)

    def update_board(self, project_id):
        self.load_sprints(project_id.board_ids)
        self.with_context(force=True).update_issue_for_sprints(project_id.sprint_ids)

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
