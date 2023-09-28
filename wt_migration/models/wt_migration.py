import ast
import requests
import json
import pytz
import logging
import base64
import time
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse
from dateutil.relativedelta import relativedelta

from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.wt_migration.utils.ac_parsing import parsing, unparsing
from odoo.addons.wt_migration.utils.mapping_table import IssueMapping, ACMapping
from odoo.addons.wt_sdk.jira.import_jira_formatter import ImportingJiraIssue, ImportingJiraWorkLog
from odoo.addons.base.models.res_partner import _tz_get

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SPECIAL_FIELDS = {'write_date', 'create_date', 'write_uid', 'create_uid'}

class UnaccessTokenUsers(models.Model):
    _name = "wt.unaccess.token"
    _description = "WT Unaccess Token"
    _order = "user_id"

    wt_migration_id = fields.Many2one("wt.migration", string="Migration")
    user_id = fields.Many2one("res.users", string="User")

class TaskMigration(models.Model):
    _name = 'wt.migration'
    _description = 'Host'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    migration_type = fields.Selection([
        ('atlassian', 'Atlassian')
    ], default='atlassian', string="Host", required=True)
    sequence = fields.Integer(string='Sequence')
    timezone = fields.Selection(_tz_get, string='Timezone', default="UTC", required=True)
    auth_type = fields.Selection([('basic', 'Basic'), ('api_token', 'API Token')], string="Authentication Type",
                                 default="api_token")
    server_type = fields.Selection([('self_hosting', 'Self-Hosted'), ('cloud', 'Cloud')], string="Server Type",
                                   default="cloud")
    import_work_log = fields.Boolean(string='Import Work Logs?')
    auto_export_work_log = fields.Boolean(string="Auto Export Work Logs?")
    is_load_acs = fields.Boolean(string="Import Checklist?")
    wt_server_url = fields.Char(string='Server Endpoint', store=True, compute="_compute_api_url", compute_sudo=True, readonly=True)
    wt_agile_url = fields.Char(string="Agile Endpoint", store=True, compute="_compute_api_url", compute_sudo=True, readonly=True)
    base_url = fields.Char(string="Domain", default="")
    admin_user_ids = fields.Many2many("res.users", string="Admins")
    active = fields.Boolean(string="Active?", default=True)
    is_round_robin = fields.Boolean(string="Share Sync?")
    full_sync = fields.Boolean(string="All Users Pull?")
    company_id = fields.Many2one('res.company', string='Company', required=True)
    template_id = fields.Many2one('wt.migration.map.template', string="Export Issue Template")
    unaccess_token_user_ids = fields.One2many("wt.unaccess.token", "wt_migration_id", string="Unaccess Token")
    allowed_user_ids = fields.Many2many("res.users", "allowed_user_migration_rel", string="Allowed Users")
    avatar = fields.Binary(string="Avatar", store=True, attachment=True)
    host_image_url = fields.Char(string="Host Image URL", compute="_compute_host_image_url", store=True)

    def name_get(self):
        name_dict = dict(self._fields['migration_type'].selection)
        ret_list = []
        for record in self:
            name = '[%s] %s' % (name_dict[record.migration_type], record.name)
            ret_list.append((record.id, name))
        return ret_list
    
    def get_prefix(self):
        self.ensure_one()
        return f"{self.migration_type}::{self.id}::"

    def get_unaccess_token_users(self):
        self.ensure_one()
        return self.unaccess_token_user_ids.mapped('user_id')
    
    def add_unaccess_token_users(self, users):
        non_existing_users = users - self.unaccess_token_user_ids.mapped('user_id')
        new_blocked_users = []
        for user in non_existing_users:
            new_blocked_users.append("(%s,%s)"%(self.id, user.id))
        
        sql_stmt = "INSERT INTO wt_unaccess_token (wt_migration_id, user_id) VALUES %s" % (",".join(new_blocked_users))
        _logger.error(sql_stmt)
        self.env.cr.execute(sql_stmt)

    def map_endpoint_url(self):
        return
    
    @api.depends('avatar')
    def _compute_host_image_url(self):
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        attachments = self.env['ir.attachment'].search([('res_model', '=', 'wt.migration'), ('res_id', 'in', self.ids), ('res_field', '=', 'avatar')])
        for migration in self:
            attachment = attachments.filtered(lambda r: r.res_id == migration.id)
            migration.host_image_url = f"{base_url}/web/image/{attachment.id}"if attachment else False

    @api.depends('base_url')
    def _compute_api_url(self):
        for migration in self:
            server_url = "https://" + urlparse(migration.base_url).netloc
            migration.base_url = server_url
            migration.wt_server_url = f"{migration.base_url}/rest/api/2"
            migration.wt_agile_url = f"{migration.base_url}/rest/agile/1.0"
            migration.map_endpoint_url()

    def __load_master_data(self):
        self.ensure_one()
        # self.load_all_users()
        # self.load_statuses()
        # self.load_types()
        # self.load_projects()
        # self.load_priorities()
        # self.load_boards()
        # own_boards = self.env['board.board'].sudo().search([('company_id', '=', self.company_id.id)])
        # self.load_sprints(own_boards)
        self.env['wt.field.map'].create_template(self)

    @api.model
    def create(self, values):
        migration = super().create(values)
        # migration.__load_master_data()
        return migration
    
    def unlink(self):
        for record in self:
            self.env['wt.status'].search([('company_id', '=', record.company_id.id)]).unlink()
            self.env['wt.type'].search([('company_id', '=', record.company_id.id)]).unlink()
            self.env['wt.field.map'].search([('migration_id', '=', record.id)]).unlink()
            self.env.cr.execute("""DELETE FROM wt_time_log WHERE company_id = %s"""%record.company_id.id)
        super().unlink()

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
        user = self.env.user
        wt_private_key = user.get_token(self)
        if self.auth_type == 'api_token':
            wt_private_key = "Basic " + base64.b64encode(
                f"{user.partner_id.email or user.login}:{wt_private_key}".encode('utf-8')).decode('utf-8')
        else:
            wt_private_key = "Bearer " + wt_private_key
        headers = {
            'Authorization': wt_private_key
        }
        return headers

    def _get_permission(self):
        self.ensure_one()
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.base_url}/rest/auth/1/session",
            'method': 'get',
        }
        response = self.make_request(request_data, headers)

    def _get_single_project(self, project_key):
        headers = self.__get_request_headers()
        result = requests.get(f"{self.wt_server_url}/project/{project_key}", headers=headers)
        record = json.loads(result.text)
        res = {
            'project_name': record['name'],
            'project_key': record['key'],
            'wt_migration_id': self.id,
            'allow_to_fetch': True,
            'allowed_manager_ids': [(4, self.env.user.id, False)],
            'company_id': self.company_id.id
        }
        return self.env['wt.project'].sudo().create(res)

    def _get_current_employee(self):
        return {
            "user_login": {user.login for user in
                           self.with_context(active_test=False).env["res.users"].sudo().search([])}
        }

    def load_all_users(self, user_email=''):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/user/search?query='{user_email}'",
            'method': 'get',
        }
        response = self.make_request(request_data, headers)
        if not isinstance(response, list):
            response = [response]
        current_employee_data = self._get_current_employee()
        UserEnv = self.env["res.users"].sudo().with_context(install_mode=True)
        users = UserEnv
        travel_login = set()
        for record in response:
            login = record['emailAddress'] or record['accountId']
            email = record['emailAddress'] or f"{record['accountId']}@mail"
            if login not in travel_login and login not in current_employee_data["user_login"]:
                new_user = UserEnv.create({
                    "name": record["displayName"],
                    "login": login,
                    'email': email,
                    'active': False,
                    'company_id': self.company_id.id,
                    'company_ids': [(6, 0, self.company_id.ids)],
                    'tz': record['timeZone'],
                    'account_id': record['accountId'],
                    'image_1920': base64.b64encode(requests.get(record["avatarUrls"]['48x48'].strip()).content).replace(b"\n", b"")
                })
                new_user.action_create_employee()
                users |= new_user
                travel_login.add(record['emailAddress'])
                
    def load_projects(self):
        self.ensure_one()
        self.env.user.token_exists_by_migration(self)
        headers = self.__get_request_headers()
        result = requests.get(f"{self.wt_server_url}/project", headers=headers)
        existing_project = self.env['wt.project'].search([])
        existing_project_dict = {f"{r.project_key}": r for r in existing_project}
        user_id = self.env.user
        new_project = []
        for record in json.loads(result.text):
            if not existing_project_dict.get(record.get('key', False), False):
                res = {
                    'project_name': record['name'],
                    'project_key': record['key'],
                    'wt_migration_id': self.id,
                    'allow_to_fetch': True,
                    'external_id': record['id'],
                    'company_id': self.company_id.id,
                }
                if user_id:
                    res['allowed_manager_ids'] = [(4, user_id.id, False)]
                new_project.append(res)
            else:
                project = existing_project_dict.get(record.get('key', False), False)
                if user_id:
                    project.sudo().allowed_manager_ids = [(4, user_id.id, False)]
        projects = self.env['wt.project']
        if new_project:
            projects = self.env['wt.project'].sudo().create(new_project)
        self.env.user.token_clear_cache()
        return projects    
    
    def load_initial_projects(self):
        return self.load_projects()
    
    # def update_projects_id(self):
    #     self.ensure_one()
    #     headers = self.__get_request_headers()
    #     result = requests.get(f"{self.wt_server_url}/project", headers=headers)
    #     existing_project = self.env['wt.project'].search([])
    #     existing_project_dict = {f"{r.project_key}": r for r in existing_project}
    #     user_id = self.env.user
    #     new_project = []
    #     for record in json.loads(result.text):
    #         if not existing_project_dict.get(record.get('key', False), False):
    #             res = {
    #                 'project_name': record['name'],
    #                 'project_key': record['key'],
    #                 'wt_migration_id': self.id,
    #                 'allow_to_fetch': True,
    #                 'company_id': self.company_id.id,
    #                 'external_id': record['id']
    #             }
    #             if user_id:
    #                 res['allowed_manager_ids'] = [(4, user_id.id, False)]
    #             new_project.append(res)
    #         else:
    #             project = existing_project_dict.get(record.get('key', False), False)
    #             if user_id:
    #                 project.sudo().allowed_manager_ids = [(4, user_id.id, False)]
    #     projects = self.env['wt.project']
    #     if new_project:
    #         projects = self.env['wt.project'].sudo().create(new_project)
    #     return projects

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
        if result.status_code >= 400:
            raise Exception(result.text)
        if result.text == "":
            return ""
        body = result.json()
        if isinstance(body, dict):
            if len(body.get('errors') or []):
                raise Exception(body.get('errors'))
            if len(body.get('errorMessages') or []):
                raise Exception(body.get('errorMessages'))
        return body
    
    def load_priorities(self):
        header = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/priority",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['wt.priority'].sudo()
        for record in response:
            env.create({
                'name': record['name'],
                'id_on_wt': record['id'],
                'icon_url': record['iconUrl'],
                'company_id': self.company_id.id,
                'wt_migration_id': self.id
            })
        
    def load_statuses(self):
        header = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/status",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['wt.status'].sudo()
        for record in response:
            env.create({
                'name': record['name'],
                'key': record['statusCategory']['key'],
                'wt_key': record['id'],
                'company_id': self.company_id.id,
                'wt_migration_id': self.id
            })
    
    def load_types(self):
        header = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.wt_server_url}/issuetype",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['wt.type'].sudo()
        for record in response:
            epic_ok = False
            if 'epic' in record['name'].lower():
                epic_ok=True
            env.create({
                'name': record['name'],
                'img_url': record['iconUrl'],
                'key': record['id'],
                'company_id': self.company_id.id,
                'wt_migration_id': self.id,
                'epic_ok': epic_ok
            })


    def get_user(self):
        return {(r.partner_id.email or r.login, self.company_id.id): r.id for r in self.env['res.users'].sudo().search([])}
    
    def __prepare_values_jira_issue(self, issue):
        res = {
            'fields': {
                'project': {'id': issue.project_id.external_id},
                'summary': issue.issue_name,
                'issuetype': {'id': issue.issue_type_id.key},
                'labels': issue.mapped('label_ids.name'),
                'description': issue.description,
                'assignee': {
                    'id': issue.assignee_id.account_id
                } if issue.assignee_id.account_id else False
            }
        }
        if issue.priority_id.id_on_wt:
            res['fields']['priority'] = {'id': issue.priority_id.id_on_wt}
        return res
    
    def __prepare_values_jira_issues(self, issues):
        values = []
        for issue in issues:
            values.append(self.__prepare_values_jira_issue(issue))
        return {
            'issueUpdates': values
        }

    @api.model
    def _create_issues(self, issues):
        issue_by_migration = defaultdict(lambda:self.env['wt.issue'])
        for issue in issues:
            if issue.wt_migration_id:
                issue_by_migration[issue.wt_migration_id] |= issue
        self.sudo()._export_issues(issue_by_migration)

    def _export_issues(self, issue_by_migration):
        # Export normal fields
        try:

            for migration, issues in issue_by_migration.items():
                server_url = urlparse(migration.wt_server_url).netloc
                header = migration.__get_request_headers()
                content = migration.__prepare_values_jira_issues(issues)
                request_data = {
                    'endpoint': f"{migration.wt_server_url}/issue/bulk",
                    'method': 'post',
                }
                request_data['body'] = content
                response = migration.make_request(request_data, header)
                dict_issues = response.get('issues') or []
                if len(issues) != len(dict_issues):
                    raise UserError("Exporting incorrect")
                for index, issue in enumerate(issues):
                    issue.update({
                        'wt_id': dict_issues[index]['id'],
                        'issue_key': dict_issues[index]['key'],
                        'issue_url': f"https://{server_url}/browse/{dict_issues[index]['key']}"
                    })
                # # Export Epics
                issue_by_sprint = defaultdict(lambda: self.env['wt.issue'])
                issue_by_epic = defaultdict(lambda: self.env['wt.issue'])
                for issue in issues:
                    if issue.epic_id:
                        issue_by_epic[issue.epic_id] |= issue
                    if issue.sprint_id:
                        issue_by_sprint[issue.sprint_id] |= issue
                if len(issue_by_epic.keys()):
                    for epic, issues in issue_by_epic.items():
                        request_data = {
                            'endpoint': f"{migration.wt_agile_url}/epic/{epic.issue_key}/issue",
                            'method': 'post',
                        }
                        request_data['body'] = {
                            "issues": issues.mapped('issue_key')
                        }
                    response = migration.make_request(request_data, header)
                if len(issue_by_sprint.keys()):
                    for sprint, issues in issue_by_sprint.items():
                        request_data = {
                            'endpoint': f"{migration.wt_agile_url}/sprint/{sprint.id_on_wt}/issue",
                            'method': 'post',
                        }
                        request_data['body'] = {
                            "issues": issues.mapped('issue_key')
                        }
                    response = migration.make_request(request_data, header)
                
        except Exception as e:
            raise UserError(str(e))
        
    def get_clone_template_rule(self, destination_migration):
        res = self.env.context.get('force_clone_template_rule')
        if not res:
            res = self.env['wt.clone.rule'].search([('src_migration_id', '=', self.id), ('dest_migration_id', '=', destination_migration.id)], limit=1)
        return res

    def load_clone_template(self, destination_migration, clone_rule):
        self.ensure_one()
        rule = self.get_clone_template_rule(destination_migration)
        template = None
        if rule:
            fields = {
                fr.field_id: (fr.template, fr.keep_raw) for fr in rule.clone_field_ids
            }
            types = dict()
            for type_rule in rule.clone_type_ids:
                for clone_type in type_rule.src_type_ids:
                    types[clone_type.id] = type_rule.dest_type_id.id
            statuses = dict()
            for status_rule in rule.clone_status_ids:
                for clone_status in status_rule.src_status_ids:
                    statuses[clone_status.id] = status_rule.dest_status_id.id
            projects = dict()
            if not clone_rule.project_id:
                for project_rule in rule.clone_project_ids:
                    for clone_project in project_rule.src_project_ids:
                        projects[clone_project.id] = project_rule.dest_project_id.id
                projects[False] = rule.default_project_id.id
            epics = dict()
            if not clone_rule.epic_id:
                for epic_rule in rule.clone_epic_ids:
                    for clone_epic in epic_rule.src_epic_ids:
                        epics[clone_epic.id] = epic_rule.dest_epic_id.id
                epics[False] = rule.default_epic_id.id
            priorities = dict()
            if not clone_rule.priority_id:
                for priority_rule in rule.clone_priority_ids:
                    for clone_priority in priority_rule.src_priority_ids:
                        priorities[clone_priority.id] = priority_rule.dest_priority_id.id
            template = {
                'fields': fields,
                'types': types,
                'statuses': statuses,
                'projects': projects,
                'epics': epics,
                'priorities': priorities
            }
        return template

    @api.model
    def minify_with_existing_record(self, curd_data, existing_record):
        index, length, keys = 0, len(curd_data.keys()), list(curd_data.keys())
        while index < length:
            if keys[index] not in SPECIAL_FIELDS:
                value = getattr(existing_record, keys[index])
                if isinstance(value, models.Model):
                    if isinstance(curd_data[keys[index]], int):
                        if value.id == curd_data[keys[index]]:
                            del curd_data[keys[index]]
                    elif not (set([x[1] for x in curd_data[keys[index]]]) - set(value.ids)):
                        del curd_data[keys[index]]
                elif isinstance(value, datetime) or isinstance(curd_data[keys[index]], datetime):
                    if value and value.isoformat()[:16] == curd_data[keys[index]].isoformat()[:16]:
                        del curd_data[keys[index]]
                elif isinstance(value, str):
                    if value.strip() == (curd_data[keys[index]] or '').strip():
                        del curd_data[keys[index]]
                elif float(value):
                    temp = curd_data[keys[index]]
                    if isinstance(temp, str):
                        try:
                            temp = "0%s"%temp if not temp.startswith('-') else temp
                            temp = float(temp) 
                        except Exception as e:
                            error_msg = "%s-%s:\n %s" % (e, str(existing_record), json.dumps(curd_data, indent=4))
                            raise Exception(error_msg)
                    if float(value) == temp:
                        del curd_data[keys[index]]
            else:
                del curd_data[keys[index]]
            index += 1
        return curd_data

    # ===========================================  Section for loading issues/issues =============================================
    @api.model
    def _create_new_acs(self, values):
        return list(map(lambda r: (0, 0, {
            'name': parsing(r.name),
            'wt_raw_name': r.name,
            "checked": r.checked,
            "key": r.key,
            "sequence": r.sequence,
            "is_header": r.is_header,
        }), values))

    def _update_acs(self, ac_ids, values=[]):
        if not values:
            return False
        value_keys = {r.key: r for r in values}
        to_delete_records = ac_ids.filtered(lambda r: r.key and r.key not in value_keys)
        ac_ids -= to_delete_records
        res = []
        res += to_delete_records.mapped(lambda r: (2, r.id))
        for record in ac_ids:
            if record.key:
                r = value_keys.get(record.key, None)
                if r:
                    if (r.is_header != record.is_header \
                            or record.sequence != r.sequence \
                            or record.checked != r.checked):
                        res.append((1, record.id, {
                            'name': parsing(r.name),
                            'wt_raw_name': r.name,
                            "checked": r.checked or record.checked,
                            "key": r.key,
                            "sequence": r.sequence,
                            "is_header": r.is_header
                        }))
                    del value_keys[record.key]
        res += self._create_new_acs(list(value_keys.values()))
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
        refresh_month = self.env['ir.config_parameter'].sudo().get_param('wt_migration.refresh_duration_month')
        if refresh_month and int(refresh_month):
            domain = domain + [('write_date' ,'>=', fields.Datetime.now() + relativedelta(months=int(refresh_month)))]
        return {
            'dict_project_key': {(r.project_key, r.company_id.id): r.id for r in
                                 self.env['wt.project'].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_user': self.sudo().with_context(active_test=False).get_user(),
            'dict_issue_key': {(r.issue_key, r.company_id.id): r for r in
                               self.env['wt.issue'].sudo().with_context(active_test=False).search(domain + [('company_id', '=', self.company_id.id)])},
            'dict_status': {(r.key, r.company_id.id): r.id for r in
                            self.env['wt.status'].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_type': {(r.key, r.company_id.id): r.id for r in self.env["wt.type"].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_sprint': {r.id_on_wt: r.id for r in
                            self.env["agile.sprint"].with_context(active_test=False).sudo().search([('company_id', '=', self.company_id.id)])},
            'dict_label': {(r.name, r.company_id.id): r.id for r in
                           self.env["wt.label"].with_context(active_test=False).sudo().search([])},
            'dict_priority': {(r.id_on_wt, r.company_id.id): r.id for r in
                              self.env['wt.priority'].with_context(active_test=False).sudo().search([])
                              },
            'dict_field_map': {r.key: r.value for r in self.env['wt.field.map'].sudo().search([('migration_id', '=', self.id), ('type', '=', 'sdk')])}
        }


    def prepare_issue_data(self, local, issue, response):
        curd_data = {
            'issue_name': issue.summary,
            'issue_key': issue.issue_key,
            'issue_url': issue.issue_url,
            'story_point': issue.hour_point and issue.hour_point or issue.fibonacci_point,
            'story_point_unit': issue.hour_point and 'hrs' or 'general',
            'wt_migration_id': self.id,
            'wt_id': issue.remote_id,
            'project_id': local['dict_project_key'].get((issue.project_key, self.company_id.id)),
            'assignee_id': local['dict_user'].get((issue.assignee_email or issue.assignee_accountId, self.company_id.id)),
            'tester_id': local['dict_user'].get((issue.tester_email or issue.tester_accountId, self.company_id.id)),
            'status_id': local['dict_status'].get((issue.status_key, self.company_id.id)),
            'issue_type_id': local['dict_type'].get((issue.issue_type_key, self.company_id.id)),
            'priority_id': local['dict_priority'].get((issue.priority_key, self.company_id.id))
        }
        if issue.epic:
            curd_data['epic_id'] = local['dict_issue_key'].get((issue.epic.issue_key, self.company_id.id)).id
        if isinstance(issue.raw_sprint, list) and len(issue.raw_sprint):
            issue.raw_sprint = issue.raw_sprint[0]
        if isinstance(issue.raw_sprint, dict) and issue.raw_sprint.get('id', None):
            sprint_id = local['dict_sprint'].get(issue.raw_sprint.get('id', None))
            if sprint_id:
                curd_data['sprint_id'] = sprint_id
            else:
                curd_data['sprint_key'] = issue.raw_sprint.get('id', None)
        if issue.labels:
            curd_data['label_ids'] = [(4, local['dict_label'][(label, self.company_id.id)]) for label in issue.labels]
        return curd_data

    def mapping_issue(self, local, issue, response):
        curd_data = self.prepare_issue_data(local, issue, response)
        index, length, keys = 0, len(curd_data.keys()), list(curd_data.keys())
        if isinstance(curd_data['story_point'], dict):
            _logger.error("ERROR AT" + str(curd_data['story_point']))
        while index < length:
            if curd_data[keys[index]] is None:
                del curd_data[keys[index]]
            index += 1
        if (issue.issue_key, self.company_id.id) not in local['dict_issue_key']:
            if self.is_load_acs and issue.checklists:
                step = self._create_new_acs(issue.checklists)
                if step:
                    curd_data['ac_ids'] = step
            response['new'].append(curd_data)
        else:
            existing_issue = local['dict_issue_key'].get((issue.issue_key, self.company_id.id))
            curd_data = self.minify_with_existing_record(curd_data, existing_issue)
            response['updated'] |= existing_issue
            if self.is_load_acs and issue.checklists:
                step = self._update_acs(existing_issue.ac_ids, issue.checklists)
                if step:
                    curd_data['ac_ids'] = step
            if len(curd_data.keys()):
                existing_issue.write(curd_data)

    def create_missing_projects(self, issues, local):
        company = self.company_id
        processed = set([False, None])
        to_create_projects = [issue.project_key for issue in issues if
                              (issue.project_key, company.id) not in local['dict_project_key']]
        if len(to_create_projects):
            new_projects = self.env['wt.project']
            for project in to_create_projects:
                if project not in processed:
                    new_project = self._get_single_project(project_key=project)
                    local['dict_project_key'][(project, company.id)] = new_project.id
                    new_projects |= new_project
                    processed.add(project)
            new_projects.cron_fetch_issue()

    def create_missing_users(self, issues, local):
        company = self.company_id
        processed = set([False, None])
        to_create_users = [(issue.assignee_email, issue.assignee_name, issue.assignee_accountId) for issue in issues if (issue.assignee_email or issue.assignee_accountId, company.id) not in local['dict_user']]
        to_create_users += [(issue.tester_email, issue.tester_name, issue.tester_accountId) for issue in issues if (issue.assignee_email or issue.tester_accountId, company.id) not in local['dict_user']]
        user_env_sudo = self.env['res.users'].sudo().with_context(install_mode=True)
        for user in to_create_users:
            login = user[0] or user[2]
            email = login or f"{user[2]}@mail"
            if login not in processed:
                new_user = user_env_sudo.create({
                    'login': login,
                    'name': user[1] or 'undefined',
                    'email': email,
                    'active': False,
                    'account_id': user[2],
                    'company_id': self.company_id.id,
                    'company_ids': [(6, 0, self.company_id.ids)],
                })
                new_user.partner_id.email = login
                new_user.action_create_employee()
                local['dict_user'][(login, company.id)] = new_user.id
                processed.add(login)

    def create_missing_statuses(self, issues, local):
        company = self.company_id
        status_env_sudo = self.env['wt.status'].sudo()
        for issue in issues:
            if (issue.remote_status_id, company.id) not in local['dict_status']:
                local['dict_status'][(issue.remote_status_id, company.id)] = status_env_sudo.create({
                    'name': issue.raw_status_key['name'],
                    'key': issue.status_key,
                    'wt_key': issue.remote_status_id,
                    'company_id': company.id,
                    'wt_migration_id': self.id
                }).id

    def create_missing_types(self, issues, local):
        company = self.company_id
        type_env_sudo = self.env['wt.type'].sudo()
        for issue in issues:
            if (issue.issue_type_key, company.id) not in local['dict_type']:
                local['dict_type'][(issue.issue_type_key, company.id)] = type_env_sudo.create({
                    'name': issue.raw_type['name'],
                    'img_url': issue.raw_type['iconUrl'],
                    'key': issue.issue_type_key,
                    'company_id': company.id,
                    'wt_migration_id': self.id
                }).id

    def create_missing_epics(self, issues, local):
        company = self.company_id
        issue_env_sudo = self.env['wt.issue'].sudo()
        for issue in issues:
            if issue.epic and (issue.epic.issue_key, company.id)  not in local['dict_issue_key']:
                epics = {'new': []}
                self.mapping_issue(local, issue.epic, epics)
                res = issue_env_sudo.with_context(default_epic_ok=True).create(epics['new'])
                local['dict_issue_key'][(res.issue_key, company.id)] = res

    def create_missing_labels(self, issues, local):
        company = self.company_id
        set_labels = set()
        for issue in issues:
            if issue.labels:
                set_labels.update(issue.labels)
        label_env_sudo = self.env['wt.label'].sudo()
        for label in set_labels:
            if (label, company.id) not in local['dict_label']:
                res = label_env_sudo.create({
                    'name': label,
                    'company_id': company.id
                })
                local['dict_label'][(label, company.id)] = res.id

    def create_missing_priorities(self, issues, local):
        company = self.company_id
        priority_env_sudo = self.env['wt.priority'].sudo()
        try:
            for issue in issues:
                if (issue.priority_key, company.id) not in local['dict_priority'] and issue.priority:
                    local['dict_priority'][(issue.priority_key, company.id)] = priority_env_sudo.create({
                    'name': issue.priority['name'],
                    'id_on_wt': issue.priority['id'],
                    'icon_url': issue.priority['iconUrl'],
                    'company_id': company.id,
                'wt_migration_id': self.id
                }).id
        except Exception as e:
            _logger.error(issue.issue_key)
            raise e

    def processing_issue_raw_data(self, local, raw):
        if not self.is_load_acs:
            local['dict_field_map']['checklist'] = False
        importing_base = ImportingJiraIssue(self.server_type, self.wt_server_url, local['dict_field_map'])
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
        self.create_missing_labels(issues, local)
        self.create_missing_priorities(issues, local)
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

        if existing_record:
            self.env.cr.execute(f"UPDATE wt_issue SET write_date = NOW() WHERE id IN %(ids)s",
                                {'ids': tuple(existing_record.ids)})
        return existing_record | self.env['wt.issue'].sudo().create(response)

    def load_issues(self, extra_jql="", domain=[], load_all=False):
        request_data = {
            'endpoint': f"{self.wt_server_url}/search",
            'params': [extra_jql]
        }
        issues =  self.do_request(request_data, domain=domain, load_all=load_all)
        self.load_boards(issues.mapped('project_id'))
        self.with_delay().update_board_by_new_issues(self.env.user, issues)

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

        self.load_boards(issue_ids.mapped('project_id'))
        self.with_delay().update_board_by_new_issues(self.env.user, issue_ids)
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

    def prepare_worklog_data(self, local, log, issue, response):
        user_id = local['dict_user'].get((log.author or log.author_accountId, self.company_id.id), False)
        if not user_id:
            _logger.info("MISSING ASSIGNEE: wt.issue(%ss)" %issue.get(log.remote_issue_id, False))
        curd_data = {
            'time': log.time,
            'duration': log.duration,
            'start_date': self.convert_server_tz_to_utc(log.start_date),
            'description': log.description or '',
            'id_on_wt': log.remote_id,
            'capture_export_duration': log.duration,
            'capture_export_start_date': self.convert_server_tz_to_utc(log.start_date),
            'capture_export_description': log.description or '',
            'user_id': user_id,
            'state': 'done',
            'source': 'sync',
            'issue_id': issue.get(log.remote_issue_id, False),
            'export_state': 1,
            'wt_create_date': self.convert_server_tz_to_utc(log.create_date),
            'wt_write_date': self.convert_server_tz_to_utc(log.write_date),
            'company_id': self.company_id.id
        }
        return curd_data

    def mapping_worklog(self, local, log, issue, response):
        curd_data = self.prepare_worklog_data(local, log, issue, response)
        if log.remote_id not in local['dict_log']:
            if log.duration > 0 and issue.get(log.remote_issue_id, False):
                response['new'].append(curd_data)
        else:
            existing_log = local['dict_log'].get(log.remote_id)
            curd_data = self.minify_with_existing_record(curd_data, existing_log)
            if len(curd_data.keys()):
                curd_data['export_state'] = 1
                existing_log.with_context(bypass_auto_delete=True).write(curd_data)
                response['updated'] |= existing_log

    def create_missing_assignee(self, logs, local):
        company = self.company_id
        processed = set([False, None])
        to_create_users = [(log.author, log.author_name, log.author_accountId) for log in logs if (log.author or log.author_accountId, company.id) not in local['dict_user']]
        user_env_sudo = self.env['res.users'].sudo().with_context(install_mode=True)
        for user in to_create_users:
            login = user[0] or user[2]
            email = login or f"{user[2]}@mail"
            if login not in processed:
                new_user = user_env_sudo.create({
                    'login': login,
                    'name': user[1],
                    'active': False,
                    'email': email,
                    'company_id': company.id,
                    'account_id': user[2],
                })
                new_user.partner_id.email = login
                new_user.action_create_employee()
                local['dict_user'][(login, company.id)] = new_user.id
                processed.add(login)

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
        self.create_missing_assignee(logs, local)
        for log in logs:
            self.mapping_worklog(local, log, issue, response)
        return response

    def load_missing_work_logs_by_unix(self, unix, users, projects, batch=900, end_unix=-1):
        if self.import_work_log:
            for user in users:
                last_page = False
                mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
                headers = self.with_user(user).__get_request_headers()
                issue_ids = self.env['wt.issue'].search([('project_id', 'in', projects.ids)])
                local_data = {
                    'dict_log': {},
                    'dict_issue': {issue_id.wt_id: issue_id.id for issue_id in issue_ids},
                    'dict_user': self.with_context(active_test=False).get_user()
                }
                flush = set()
                to_create = []
                request_data = {
                    'endpoint': f"{self.wt_server_url}/worklog/updated?since={unix}",
                }
                page_failed_count = 0
                page_break = False
                while not last_page and page_failed_count < 6 and not page_break:
                    body = self.make_request(request_data, headers)
                    if isinstance(body, dict):
                        page_failed_count = 0
                        request_data['endpoint'] = body.get('nextPage', '')
                        last_page = body.get('lastPage', True)
                        ids = list(map(lambda r: r['worklogId'], body.get('values', [])))
                        flush.update(ids)
                        log_failed_count = 0
                        while log_failed_count < 6:
                            if len(flush) > batch or last_page:
                                self.env.cr.execute("""
                                    SELECT ARRAY_AGG(id_on_wt) AS result FROM wt_time_log WHERE id_on_wt IN %(ids)s AND project_id NOT IN %(project_ids)s
                                """, {
                                    'ids': tuple(flush),
                                    'project_ids': tuple(projects.ids)
                                })
                                res = self.env.cr.dictfetchone()
                                flush -= set(res['result'] or [])
                                if len(flush):
                                    request = {
                                        'endpoint': f"{self.wt_server_url}/worklog/list",
                                        'method': 'post',
                                        'body': {'ids': list(flush)}
                                    }
                                    logs = self.make_request(request, headers)
                                    if isinstance(logs, list):
                                        log_failed_count = 0
                                        data = {'worklogs': logs}
                                        new_logs = self.processing_worklog_raw_data(local_data, data, mapping)
                                        to_create.extend(new_logs.get('new'))
                                        flush = set()
                                        break
                                    else:
                                        _logger.warning(f"WORK LOG LOAD FAILED COUNT: {log_failed_count}")
                                        log_failed_count += 1
                                        time.sleep(30)
                                        continue
                                else:
                                    break
                        del body['values']
                        if end_unix > 0 and end_unix > body.get('until', 0):
                            last_page = True
                    else:
                        _logger.warning(f"PAGE LOAD FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue
                if len(to_create):
                    self.env["wt.time.log"].with_context(bypass_rounding=True).create(to_create)

    def load_work_logs_by_unix(self, unix, users, batch=900, end_unix=-1):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            for user in users:
                last_page = False
                mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
                headers = self.with_user(user).__get_request_headers()
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
                page_break = False
                while not last_page and page_failed_count < 6 and not page_break:
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
                        if end_unix > 0 and end_unix > body.get('until', 0):
                            last_page = True
                    else:
                        _logger.warning(f"PAGE LOAD FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue
                if len(to_create):
                    self.env["wt.time.log"].create(to_create)

    def delete_work_logs_by_unix(self, unix, users, batch=900):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            for user in users:
                last_page = False
                headers = self.with_user(user).__get_request_headers()
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
                    else:
                        _logger.warning(f"PAGE DELETED FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue

    def load_work_logs(self, issue_ids, paging=100, domain=[], load_all=False):
        self = self.with_context(bypass_cross_user=True)
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

    def load_work_log_by_ids_raw(self, ids, users):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            new_logs = []
            for user in users:
                mapping = ImportingJiraWorkLog(self.server_type, self.wt_server_url)
                headers = self.with_user(user).__get_request_headers()
                local_data = {'dict_user': {}}
                request = {
                    'endpoint': f"{self.wt_server_url}/worklog/list",
                    'method': 'post',
                    'body': {'ids': ids}
                }
                logs = self.make_request(request, headers)
                logs = mapping.parse_logs(logs)
                for log in logs:
                    new_logs.append(self.prepare_worklog_data(local_data, log, {}, {}))
                wt_ids = list(map(lambda r: r['id_on_wt'], new_logs))
                if set(ids) - set(wt_ids):
                    break
                else:
                    continue
            return new_logs
        return []

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
        time_log_ids.export_state = 1

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
        time_log_ids.export_state = 1

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

    def _update_project(self, project_id, project_last_update):
        self = self.with_context(bypass_cross_user=True)
        updated_date = datetime(1970, 1, 1, 1, 1, 1, 1)
        if project_last_update:
            updated_date = self.convert_utc_to_usertz(project_last_update)
        str_updated_date = updated_date.strftime('%Y-%m-%d %H:%M')
        params = f"""jql=project="{project_id.project_key}" AND updated >= '{str_updated_date}'"""
        request_data = {'endpoint': f"{self.wt_server_url}/search", "params": [params]}
        issue_ids = self.do_request(request_data, load_all=True)
        _logger.info(f"{project_id.project_name}: {len(issue_ids)}")

    def update_project(self, project_id, user_id):
        _self = self.with_user(user_id)
        _self.with_delay()._update_project(project_id, project_id.last_update)

    def update_projects(self, latest_unix, project_by_user_id):
        self = self.with_context(bypass_cross_user=True)
        for user_id, projects in project_by_user_id.items():
            user = self.env['res.users'].browse(int(user_id)).exists()
            self = self.with_user(user)
            str_updated_date = self.convert_utc_to_usertz(datetime.fromtimestamp(latest_unix / 1000)).strftime(
                '%Y-%m-%d %H:%M')
            query_projects = ",".join(projects.mapped(lambda p: f'"{p.project_key}"'))
            params = f"""jql=updated >= '{str_updated_date}' AND PROJECT IN ({query_projects})"""
            request_data = {'endpoint': f"{self.wt_server_url}/search", "params": [params]}

            issue_ids = self.do_request(request_data, load_all=True)

            _logger.info(f"Batch Load Of User {user.display_name}: {len(issue_ids)}")
            self.load_boards(projects)
            self.with_delay().update_board_by_new_issues(user_id, issue_ids)

    def load_boards(self, project_ids=False):
        self.ensure_one()
        if not self.wt_agile_url:
            return
        if not project_ids:
            project_ids = self.env["wt.project"].sudo().search([])
        project_by_key = {project.project_key: project for project in project_ids}
        existed_boards = set(project_ids.mapped('board_ids').mapped('id_on_wt'))
        allowed_user_ids = self.admin_user_ids
        if self.is_round_robin:
            allowed_user_ids = project_ids.mapped('allowed_manager_ids')
        allowed_user_ids = allowed_user_ids.token_exists_by_migration(self)
        if not allowed_user_ids:
            return
        for user in allowed_user_ids:
            headers =  self.with_user(user).__get_request_headers()
            request_data = {
                'endpoint': f"""{self.wt_agile_url}/board""",
                'method': 'get'
            }
            start_index, page_size, total_response, paging = 0, 50, 51, 50
            while start_index < total_response:
                page_size = paging if total_response - start_index > paging else total_response - start_index
                request_data['params'] = [f'startAt={start_index}', f'maxResults={page_size}']
                data = self.make_request(request_data, headers) or {}
                total_response = data.get('total', 1)
                start_index += paging
                for board in data.get('values', []):
                    if board.get('id') not in existed_boards:
                        project = project_by_key.get(board.get('location', {}).get('projectKey', ''))
                        if project:
                            self.env["board.board"].sudo().create({
                                'id_on_wt': board['id'],
                                'name': board['name'],
                                'type': board['type'],
                                'project_id': project.id,
                            })
        self.env.user.token_clear_cache()

    def prepare_local_agile(self):
        company_id = self.company_id.id
        return {
            'sprints': {x.id_on_wt: x for x in self.env['agile.sprint'].sudo().search([('company_id', '=', company_id)])},
            'boards': {x.id_on_wt: x for x in self.env['board.board'].sudo().search([('company_id', '=', company_id)])},
        }

    def _map_sprint_values(self, sprint_data, local):
        agile_env_sudo = self.env["agile.sprint"].sudo()
        context_board = self.env.context.get('board') 
        default_board = self.env['board.board']
        try:
            for sprint in sprint_data:
                existing_board = local['boards'].get(sprint.get('originBoardId')) or context_board or default_board
                if sprint['id'] not in local['sprints']:
                    sprint = agile_env_sudo.create({
                        'id_on_wt': sprint['id'],
                        'name': sprint['name'],
                        'state': sprint['state'],
                        'project_id': existing_board.project_id.id,
                        'board_id': existing_board.id,
                        'updated': True
                    })
                    local['sprints'][sprint.id_on_wt] = sprint
                elif sprint['state'] != local['sprints'][sprint['id']].state:
                    local['sprints'][sprint['id']].sudo().write({
                        'state': sprint['state'],
                        'updated': True
                    })
        except Exception as e:
            raise e

    def __get_sprints_by_board(self, board, local):
        board.ensure_one()
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"""{self.wt_agile_url}/board/{board.id_on_wt}/sprint?maxResults=50""",
            'method': 'get',
        }
        data = self.make_request(request_data, headers)
        self._map_sprint_values(data.get('values') or [], local)

    def __get_sprint_by_id(self, sprint_id, local):
        try:
            headers = self.__get_request_headers()
            request_data = {
                'endpoint': f"""{self.wt_agile_url}/sprint/{sprint_id}""",
                'method': 'get',
            }
            data = self.make_request(request_data, headers)
            self._map_sprint_values([data], local)
        except Exception as e:
            raise e

    def update_issue_for_sprints(self, sprint_ids=False):
        if not sprint_ids:
            sprint_ids = self.env["agile.sprint"].sudo().search([])
        sprint_by_id = {sprint.id_on_wt: sprint for sprint in sprint_ids}
        issues = self.env['wt.issue'].sudo().search([('sprint_key', 'in', sprint_ids.mapped('id_on_wt'))])
        for issue in issues:
            issue.write({'sprint_id': sprint_by_id[issue.sprint_key], 'sprint_key': False})

    def update_board_by_new_issues(self, user, issues):
        local = self.prepare_local_agile()
        existing_sprints = issues.mapped('sprint_id')
        existing_boards = existing_sprints.mapped('board_id')
        self = self.with_user(user)
        for board in existing_boards:
            self.with_context(board=board).__get_sprints_by_board(board, local)

        new_sprint_ids = issues.filtered('sprint_key').mapped('sprint_key')
        existing_sprint_ids = self.env['board.board'].sudo().search([('id_on_wt', 'in', new_sprint_ids)]).ids
        gap_sprint_ids = set(new_sprint_ids) - set(existing_sprint_ids)
        if gap_sprint_ids:
            for sprint_id in gap_sprint_ids:
                self.__get_sprint_by_id(sprint_id, local)

        sprints = self.env['agile.sprint'].sudo().search([('id_on_wt', 'in', new_sprint_ids)])
        self.update_issue_for_sprints(sprints)

    # Agile Connection

    def load_sprints(self, board_ids=False):
        self.ensure_one()
        if not self.wt_agile_url:
            return
        if not board_ids:
            board_ids = self.env['board.board'].sudo().search([])
        allowed_user_ids = self.admin_user_ids
        if self.is_round_robin:
            allowed_user_ids = self.env['res.users'].search([])
        allowed_user_ids = allowed_user_ids.token_exists_by_migration(self)
        header_by_user = dict()
        board_ids = board_ids.filtered(lambda r: r.type == "scrum")
        local = self.prepare_local_agile()
        for board in board_ids:
            try:
                if not board.id_on_wt and not board.type == 'scrum':
                    continue
                usable_user = (board.project_id.allowed_manager_ids & allowed_user_ids)
                if not usable_user:
                    continue
                headers = header_by_user.get(usable_user[0]) or self.with_user(usable_user[0]).__get_request_headers()
                if usable_user[0] not in header_by_user:
                    header_by_user[usable_user[0]] = headers
                request_data = {
                    'endpoint': f"""{self.wt_agile_url}/board/{board.id_on_wt}/sprint?maxResults=50""",
                    'method': 'get',
                }
                data = self.make_request(request_data, headers)
                self.with_context(board=board)._map_sprint_values(data.get('values') or [], local)
            except Exception as e:
                _logger.error(e)

        self.env.user.token_clear_cache()
