import re
import json
import logging
import base64
import time
import traceback
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse
import requests
import pytz
from dateutil.relativedelta import relativedelta

from odoo.addons.work_abc_management.utils.search_parser import get_search_request
from odoo.addons.work_base_integration.utils.ac_parsing import parsing, unparsing
from odoo.addons.work_base_integration.utils.mapping_table import TaskMapping, ACMapping
from odoo.addons.work_sdk.jira.import_jira_formatter import ImportingJiraTask, ImportingJiraWorkLog
from odoo.addons.base.models.res_partner import _tz_get
from odoo.addons.work_base_integration.utils.urls import find_url

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import re



_logger = logging.getLogger(__name__)

SPECIAL_FIELDS = {'write_date', 'create_date', 'write_uid', 'create_uid'}

class UnaccessTokenUsers(models.Model):
    _name = "work.unaccess.token"
    _description = "WT Unaccess Token"
    _order = "user_id"

    host_id = fields.Many2one("work.base.integration", string="Host")
    user_id = fields.Many2one("res.users", string="User")

class TaskHost(models.Model):
    _name = 'work.base.integration'
    _description = 'Host'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    host_type = fields.Selection([
        ('atlassian', 'Atlassian')
    ], default='atlassian', string="Host", required=True)
    sequence = fields.Integer(string='Sequence')
    timezone = fields.Selection(_tz_get, string='Timezone', default="UTC", required=True)
    auth_type = fields.Selection([('basic', 'Basic'), ('api_token', 'API Token')], string="Authentication Type",
                                 default="api_token")
    host_service = fields.Selection([('self_hosting', 'Self-Hosted'), ('cloud', 'Cloud')], string="Server Type",
                                   default="cloud")
    import_work_log = fields.Boolean(string='Import Work Logs?')
    auto_export_work_log = fields.Boolean(string="Auto Export Work Logs?")
    is_load_acs = fields.Boolean(string="Import Checklist?")
    work_host_url = fields.Char(string='Server Endpoint', store=True, compute="_compute_api_url", compute_sudo=True, readonly=True)
    work_agile_url = fields.Char(string="Agile Endpoint", store=True, compute="_compute_api_url", compute_sudo=True, readonly=True)
    base_url = fields.Char(string="Domain", default="")
    admin_user_ids = fields.Many2many("res.users", string="Admins")
    active = fields.Boolean(string="Active?", default=True)
    is_round_robin = fields.Boolean(string="Share Sync?")
    full_sync = fields.Boolean(string="All Users Pull?")
    company_id = fields.Many2one('res.company', string='Company', required=True)
    template_id = fields.Many2one('work.base.integration.map.template', string="Export Task Template")
    unaccess_token_user_ids = fields.One2many("work.unaccess.token", "host_id", string="Unaccess Token")
    allowed_user_ids = fields.Many2many("res.users", "allowed_user_host_rel", string="Allowed Users")
    avatar = fields.Binary(string="Avatar", store=True, attachment=True)
    host_image_url = fields.Char(string="Host Image URL", compute="_compute_host_image_url")
    base_task_url = fields.Char(string="Task URL Template")

    @api.depends('host_type', 'name')
    def _compute_display_name(self):
        name_dict = dict(self._fields['host_type'].selection)
        for record in self:
            record.display_name = '[%s] %s' % (name_dict[record.host_type], record.name)
    
    def get_prefix(self):
        self.ensure_one()
        return f"{self.host_type}::{self.id}::"

    def get_unaccess_token_users(self):
        self.ensure_one()
        return self.unaccess_token_user_ids.mapped('user_id')
    
    def add_unaccess_token_users(self, users):
        non_existing_users = users - self.unaccess_token_user_ids.mapped('user_id')
        new_blocked_users = []
        for user in non_existing_users:
            new_blocked_users.append("(%s,%s)"%(self.id, user.id))
        
        sql_stmt = "INSERT INTO work_unaccess_token (host_id, user_id) VALUES %s" % (",".join(new_blocked_users))
        _logger.error(sql_stmt)
        self.env.cr.execute(sql_stmt)

    def map_endpoint_url(self):
        return
    
    def get_linked_avatar(self):
        return self.env['ir.attachment'].search([('res_model', '=', 'work.base.integration'), ('res_id', 'in', self.ids), ('res_field', '=', 'avatar')])
    
    @api.depends('avatar')
    def _compute_host_image_url(self):
        env = self.env['ir.config_parameter'].sudo()
        base_url = env.get_param('web.public.url') or env.get_param('web.base.url')
        attachments = self.get_linked_avatar()
        for host in self:
            attachment = attachments.filtered(lambda r: r.res_id == host.id)
            host.host_image_url = f"{base_url}/web/image/{attachment.id}"if attachment else False

    @api.depends('base_url')
    def _compute_api_url(self):
        for host in self:
            host_url = "https://" + urlparse(host.base_url).netloc
            host.base_url = host_url
            host.work_host_url = f"{host.base_url}/rest/api/2"
            host.work_agile_url = f"{host.base_url}/rest/agile/1.0"
            host.map_endpoint_url()

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
        self.env['work.field.map'].create_template(self)

    @api.model
    def create(self, values):
        host = super().create(values)
        host.__load_master_data()
        if 'avatar' in values:
            host.get_linked_avatar().write({'public': True})
        return host
    
    def write(self, values):
        res = super().write(values)
        if 'avatar' in values:
            self.get_linked_avatar().write({'public': True})
        return res
    
    def unlink(self):
        for record in self:
            self.env['work.status'].search([('company_id', '=', record.company_id.id)]).unlink()
            self.env['work.type'].search([('company_id', '=', record.company_id.id)]).unlink()
            self.env['work.field.map'].search([('host_id', '=', record.id)]).unlink()
            self.env.cr.execute("""DELETE FROM work_time_log WHERE company_id = %s"""%record.company_id.id)
        super().unlink()

    def action_toggle(self):
        for record in self:
            record.active = not record.active

    def convert_host_tz_to_utc(self, timestamp):
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
        work_private_key = user.get_token(self)
        if self.auth_type == 'api_token':
            work_private_key = "Basic " + base64.b64encode(
                f"{user.partner_id.email or user.login}:{work_private_key}".encode('utf-8')).decode('utf-8')
        else:
            work_private_key = "Bearer " + work_private_key
        headers = {
            'Authorization': work_private_key
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
        result = requests.get(f"{self.work_host_url}/project/{project_key}", headers=headers)
        record = json.loads(result.text)
        res = {
            'project_name': record['name'],
            'project_key': record['key'],
            'host_id': self.id,
            'allow_to_fetch': True,
            'allowed_manager_ids': [(4, self.env.user.id, False)],
            'company_id': self.company_id.id
        }
        return self.env['work.project'].sudo().create(res)

    def _get_current_employee(self):
        return {
            "user_login": {user.login for user in
                           self.with_context(active_test=False).env["res.users"].sudo().search([])}
        }

    def load_all_users(self, user_email=''):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/user/search?query='{user_email}'",
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
        self.env.user.token_exists_by_host(self)
        headers = self.__get_request_headers()
        result = requests.get(f"{self.work_host_url}/project", headers=headers)
        existing_project = self.env['work.project'].search([])
        existing_project_dict = {f"{r.project_key}": r for r in existing_project}
        user_id = self.env.user
        new_project = []
        for record in json.loads(result.text):
            if not existing_project_dict.get(record.get('key', False), False):
                res = {
                    'project_name': record['name'],
                    'project_key': record['key'],
                    'host_id': self.id,
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
        projects = self.env['work.project']
        if new_project:
            projects = self.env['work.project'].sudo().create(new_project)
        self.env.user.token_clear_cache()
        return projects    
    
    def load_initial_projects(self):
        return self.load_projects()

    def get_host_by_endpoint(self, endpoint=""):
        _self = self
        if not _self:
            _self =  self.search([])
        host_id = False
        for host in _self:
            host_by_loc = urlparse(host.base_url).netloc
            endpoint_loc = urlparse(endpoint).netloc
            if endpoint_loc == host_by_loc:
                host_id = host
                break
        return host_id
    
    def get_host_by_key(self, task_key=""):
        splitted_params = (task_key or "").strip().split('-')
        host = False
        if len(splitted_params) == 2:
            host = self.env['work.project'].search([('project_key', '=', splitted_params[0])], limit=1).host_id
        return host

    def _fetch_atlassian_task_by_endpoint(self, endpoint):
        self.ensure_one()
        host_by_loc = urlparse(self.base_url).netloc
        endpoint_loc = urlparse(endpoint).netloc
        if host_by_loc != endpoint_loc:
            raise UserError(_(f"Cannot Fetch task of another enpoint: {host_by_loc} and {endpoint_loc}"))
        match = re.search(r"(?<=browse\/)[a-zA-Z0-9]+-[a-zA-Z0-9]+", endpoint)
        if not match:
            raise UserError(_(f"Cannot find the task on the system {host_by_loc}: \n {endpoint}"))
        if match:
            match = match[0]
        return match

    def fetch_task_by_enpoint(self, endpoint=""):
        self.ensure_one()
        function = getattr(self, "_fetch_%s_task_by_endpoint"%(self.host_type))
        return function(endpoint)

    # @api.model
    # def search_task_by_link(self, link):
    #     host = self.get_host_by_endpoint(link)
    #     return host.fetch_task_by_enpoint(link)

    # @api.model
    # def query_standard_task(self, task_key):
    #     return self._search_load({"task": task_key})

    @api.model
    def get_host_by_query_string(self, query):
        urls = find_url(query)
        if len(urls):
            host = self.get_host_by_endpoint(urls[0])
        else:
            host = self.get_host_by_key(query)
        return host, len(urls)

    @api.model
    def get_host_and_task_by_query(self, query):
        host, url_mode = self.get_host_by_query_string(query)
        task_key = False
        if url_mode:
            try:
                task_key = host.fetch_task_by_enpoint(query)
            except Exception as e:
                _logger.error(str(e))
        if not task_key:
            host = False
        return host, task_key

    def query_candidate_task(self, query):
        to_fetch = False
        res = get_search_request(query)
        urls = find_url(query)
        if urls:
            query = urls[0]
            to_fetch = True
        if not to_fetch and 'task' in res:
            query = res['task']
            to_fetch = True
        if not to_fetch:
            return self.env['work.task']
        finding_host, task_key = self.get_host_and_task_by_query(query)
        host = self or finding_host
        if not host:
            raise UserError("Cannot find host for query %s, %s"%(query, task_key))
        return host._search_load({"task": task_key})

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
            'endpoint': f"{self.work_host_url}/priority",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['work.priority'].sudo()
        for record in response:
            env.create({
                'name': record['name'],
                'id_onhost': record['id'],
                'icon_url': record['iconUrl'],
                'company_id': self.company_id.id,
                'host_id': self.id
            })
        
    def load_statuses(self):
        header = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/status",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['work.status'].sudo()
        for record in response:
            env.create({
                'name': record['name'],
                'key': record['statusCategory']['key'],
                'work_key': record['id'],
                'company_id': self.company_id.id,
                'host_id': self.id
            })
    
    def load_types(self):
        header = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/issuetype",
            'method': 'get',
        }
        response = self.make_request(request_data, header)
        env = self.env['work.type'].sudo()
        for record in response:
            epic_ok = False
            if 'epic' in record['name'].lower():
                epic_ok=True
            env.create({
                'name': record['name'],
                'img_url': record['iconUrl'],
                'key': record['id'],
                'company_id': self.company_id.id,
                'host_id': self.id,
                'epic_ok': epic_ok
            })


    def get_user(self):
        return {(r.partner_id.email or r.login, self.company_id.id): r.id for r in self.env['res.users'].sudo().search([])}
    
    def __prepare_values_jira_task(self, task):
        res = {
            'fields': {
                'project': {'id': task.project_id.external_id},
                'summary': task.task_name,
                'issuetype': {'id': task.task_type_id.key},
                'labels': task.mapped('label_ids.name'),
                'description': task.description,
                'assignee': {
                    'id': task.assignee_id.account_id
                } if task.assignee_id.account_id else False
            }
        }
        if task.priority_id.id_onhost:
            res['fields']['priority'] = {'id': task.priority_id.id_onhost}
        return res
    
    def __prepare_values_jira_tasks(self, tasks):
        values = []
        for task in tasks:
            values.append(self.__prepare_values_jira_task(task))
        return {
            'taskUpdates': values
        }

    @api.model
    def _create_tasks(self, tasks):
        task_by_host = defaultdict(lambda:self.env['work.task'])
        for task in tasks:
            if task.host_id:
                task_by_host[task.host_id] |= task
        self.sudo()._export_tasks(task_by_host)

    def _export_tasks(self, task_by_host):
        # Export normal fields
        try:

            for host, tasks in task_by_host.items():
                host_url = urlparse(host.work_host_url).netloc
                header = host.__get_request_headers()
                content = host.__prepare_values_jira_tasks(tasks)
                request_data = {
                    'endpoint': f"{host.work_host_url}/issue/bulk",
                    'method': 'post',
                }
                request_data['body'] = content
                response = host.make_request(request_data, header)
                dict_tasks = response.get('tasks') or []
                if len(tasks) != len(dict_tasks):
                    raise UserError("Exporting incorrect")
                for index, task in enumerate(tasks):
                    task.update({
                        'work_id': dict_tasks[index]['id'],
                        'task_key': dict_tasks[index]['key'],
                        'task_url': f"https://{host_url}/browse/{dict_tasks[index]['key']}"
                    })
                # # Export Epics
                task_by_sprint = defaultdict(lambda: self.env['work.task'])
                task_by_epic = defaultdict(lambda: self.env['work.task'])
                for task in tasks:
                    if task.epic_id:
                        task_by_epic[task.epic_id] |= task
                    if task.sprint_id:
                        task_by_sprint[task.sprint_id] |= task
                if len(task_by_epic.keys()):
                    for epic, tasks in task_by_epic.items():
                        request_data = {
                            'endpoint': f"{host.work_agile_url}/epic/{epic.task_key}/issue",
                            'method': 'post',
                        }
                        request_data['body'] = {
                            "tasks": tasks.mapped('task_key')
                        }
                    response = host.make_request(request_data, header)
                if len(task_by_sprint.keys()):
                    for sprint, tasks in task_by_sprint.items():
                        request_data = {
                            'endpoint': f"{host.work_agile_url}/sprint/{sprint.id_onhost}/issue",
                            'method': 'post',
                        }
                        request_data['body'] = {
                            "tasks": tasks.mapped('task_key')
                        }
                    response = host.make_request(request_data, header)
                
        except Exception as e:
            raise UserError(str(e))
        
    def get_clone_template_rule(self, destination_host):
        res = self.env.context.get('force_clone_template_rule')
        if not res:
            res = self.env['work.clone.rule'].search([('src_host_id', '=', self.id), ('dest_host_id', '=', destination_host.id)], limit=1)
        return res

    def load_clone_template(self, destination_host, clone_rule):
        self.ensure_one()
        rule = self.get_clone_template_rule(destination_host)
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

    # ===========================================  Section for loading tasks/issues =============================================
    @api.model
    def _create_new_acs(self, values):
        return list(map(lambda r: (0, 0, {
            'name': parsing(r.name),
            'work_raw_name': r.name,
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
                            'work_raw_name': r.name,
                            "checked": r.checked or record.checked,
                            "key": r.key,
                            "sequence": r.sequence,
                            "is_header": r.is_header
                        }))
                    del value_keys[record.key]
        res += self._create_new_acs(list(value_keys.values()))
        return res

    def export_acceptance_criteria(self, task_id):
        task_mapping = TaskMapping(self.work_host_url, self.host_service)
        ac_mapping = ACMapping(self.work_host_url, self.host_service).exporting()
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/issue/{task_id.task_key}",
            'method': 'put',
        }
        updated_acs = ac_mapping(task_id.ac_ids)
        payload = {
            "fields": {
                f"{task_mapping.acceptance_criteria[0]}": updated_acs
            }
        }
        request_data['body'] = payload
        res = self.make_request(request_data, headers)
        return res

    def get_local_task_data(self, domain=[]):
        refresh_month = self.env['ir.config_parameter'].sudo().get_param('work_base_integration.refresh_duration_month')
        if refresh_month and int(refresh_month):
            domain = domain + [('write_date' ,'>=', fields.Datetime.now() + relativedelta(months=int(refresh_month)))]
        return {
            'dict_project_key': {(r.project_key, r.company_id.id): r.id for r in
                                 self.env['work.project'].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_user': self.sudo().with_context(active_test=False).get_user(),
            'dict_task_key': {(r.task_key, r.company_id.id): r for r in
                               self.env['work.task'].sudo().with_context(active_test=False).search(domain + [('company_id', '=', self.company_id.id)])},
            'dict_status': {(r.key, r.company_id.id): r.id for r in
                            self.env['work.status'].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_type': {(r.key, r.company_id.id): r.id for r in self.env["work.type"].sudo().with_context(active_test=False).search([('company_id', '=', self.company_id.id)])},
            'dict_sprint': {r.id_onhost: r.id for r in
                            self.env["agile.sprint"].with_context(active_test=False).sudo().search([('company_id', '=', self.company_id.id)])},
            'dict_label': {(r.name, r.company_id.id): r.id for r in
                           self.env["work.label"].with_context(active_test=False).sudo().search([])},
            'dict_priority': {(r.id_onhost, r.company_id.id): r.id for r in
                              self.env['work.priority'].with_context(active_test=False).sudo().search([])
                              },
            'dict_field_map': {r.key: r.value for r in self.env['work.field.map'].sudo().search([('host_id', '=', self.id), ('type', '=', 'sdk')])}
        }


    def prepare_task_data(self, local, task, response):
        curd_data = {
            'task_name': task.summary,
            'task_key': task.task_key,
            'task_url': task.task_url,
            'story_point': task.hour_point and task.hour_point or task.fibonacci_point,
            'story_point_unit': task.hour_point and 'hrs' or 'general',
            'host_id': self.id,
            'work_id': task.remote_id,
            'project_id': local['dict_project_key'].get((task.project_key, self.company_id.id)),
            'assignee_id': local['dict_user'].get((task.assignee_email or task.assignee_accountId, self.company_id.id)),
            'tester_id': local['dict_user'].get((task.tester_email or task.tester_accountId, self.company_id.id)),
            'status_id': local['dict_status'].get((task.status_key, self.company_id.id)),
            'task_type_id': local['dict_type'].get((task.task_type_key, self.company_id.id)),
            'priority_id': local['dict_priority'].get((task.priority_key, self.company_id.id))
        }
        if task.epic:
            curd_data['epic_id'] = local['dict_task_key'].get((task.epic.task_key, self.company_id.id)).id
        if isinstance(task.raw_sprint, list) and len(task.raw_sprint):
            task.raw_sprint = task.raw_sprint[0]
        if isinstance(task.raw_sprint, dict) and task.raw_sprint.get('id', None):
            sprint_id = local['dict_sprint'].get(task.raw_sprint.get('id', None))
            if sprint_id:
                curd_data['sprint_id'] = sprint_id
            else:
                curd_data['sprint_key'] = task.raw_sprint.get('id', None)
        if task.labels:
            curd_data['label_ids'] = [(4, local['dict_label'][(label, self.company_id.id)]) for label in task.labels]
        return curd_data

    def mapping_task(self, local, task, response):
        curd_data = self.prepare_task_data(local, task, response)
        index, length, keys = 0, len(curd_data.keys()), list(curd_data.keys())
        if isinstance(curd_data['story_point'], dict):
            _logger.error("ERROR AT" + str(curd_data['story_point']))
        while index < length:
            if curd_data[keys[index]] is None:
                del curd_data[keys[index]]
            index += 1
        if (task.task_key, self.company_id.id) not in local['dict_task_key']:
            if self.is_load_acs and task.checklists:
                step = self._create_new_acs(task.checklists)
                if step:
                    curd_data['ac_ids'] = step
            response['new'].append(curd_data)
        else:
            existing_task = local['dict_task_key'].get((task.task_key, self.company_id.id))
            curd_data = self.minify_with_existing_record(curd_data, existing_task)
            response['updated'] |= existing_task
            if self.is_load_acs and task.checklists:
                step = self._update_acs(existing_task.ac_ids, task.checklists)
                if step:
                    curd_data['ac_ids'] = step
            if len(curd_data.keys()):
                existing_task.write(curd_data)

    def create_missing_projects(self, tasks, local):
        company = self.company_id
        processed = set([False, None])
        to_create_projects = [task.project_key for task in tasks if
                              (task.project_key, company.id) not in local['dict_project_key']]
        if len(to_create_projects):
            new_projects = self.env['work.project']
            for project in to_create_projects:
                if project not in processed:
                    new_project = self._get_single_project(project_key=project)
                    local['dict_project_key'][(project, company.id)] = new_project.id
                    new_projects |= new_project
                    processed.add(project)
            new_projects.cron_fetch_task()

    def create_missing_users(self, tasks, local):
        company = self.company_id
        processed = set([False, None])
        to_create_users = [(task.assignee_email, task.assignee_name, task.assignee_accountId) for task in tasks if (task.assignee_email or task.assignee_accountId, company.id) not in local['dict_user']]
        to_create_users += [(task.tester_email, task.tester_name, task.tester_accountId) for task in tasks if (task.assignee_email or task.tester_accountId, company.id) not in local['dict_user']]
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

    def create_missing_statuses(self, tasks, local):
        company = self.company_id
        status_env_sudo = self.env['work.status'].sudo()
        for task in tasks:
            if (task.remote_status_id, company.id) not in local['dict_status']:
                local['dict_status'][(task.remote_status_id, company.id)] = status_env_sudo.create({
                    'name': task.raw_status_key['name'],
                    'key': task.status_key,
                    'work_key': task.remote_status_id,
                    'company_id': company.id,
                    'host_id': self.id
                }).id

    def create_missing_types(self, tasks, local):
        company = self.company_id
        type_env_sudo = self.env['work.type'].sudo()
        for task in tasks:
            if (task.task_type_key, company.id) not in local['dict_type']:
                local['dict_type'][(task.task_type_key, company.id)] = type_env_sudo.create({
                    'name': task.raw_type['name'],
                    'img_url': task.raw_type['iconUrl'],
                    'key': task.task_type_key,
                    'company_id': company.id,
                    'host_id': self.id
                }).id

    def create_missing_epics(self, tasks, local):
        company = self.company_id
        task_env_sudo = self.env['work.task'].sudo()
        for task in tasks:
            if task.epic and (task.epic.task_key, company.id)  not in local['dict_task_key']:
                epics = {'new': []}
                self.mapping_task(local, task.epic, epics)
                res = task_env_sudo.with_context(default_epic_ok=True).create(epics['new'])
                local['dict_task_key'][(res.task_key, company.id)] = res

    def create_missing_labels(self, tasks, local):
        company = self.company_id
        set_labels = set()
        for task in tasks:
            if task.labels:
                set_labels.update(task.labels)
        label_env_sudo = self.env['work.label'].sudo()
        for label in set_labels:
            if (label, company.id) not in local['dict_label']:
                res = label_env_sudo.create({
                    'name': label,
                    'company_id': company.id
                })
                local['dict_label'][(label, company.id)] = res.id

    def create_missing_priorities(self, tasks, local):
        company = self.company_id
        priority_env_sudo = self.env['work.priority'].sudo()
        try:
            for task in tasks:
                if (task.priority_key, company.id) not in local['dict_priority'] and task.priority:
                    local['dict_priority'][(task.priority_key, company.id)] = priority_env_sudo.create({
                    'name': task.priority['name'],
                    'id_onhost': task.priority['id'],
                    'icon_url': task.priority['iconUrl'],
                    'company_id': company.id,
                'host_id': self.id
                }).id
        except Exception as e:
            _logger.error(task.task_key)
            raise e

    def processing_task_raw_data(self, local, raw):
        if not self.is_load_acs:
            local['dict_field_map']['checklist'] = False
        importing_base = ImportingJiraTask(self.host_service, self.work_host_url, local['dict_field_map'])
        response = {
            'new': [],
            'updated': self.env['work.task']
        }
        raw_tasks = raw.get('tasks', [raw])
        tasks = importing_base.parse_tasks(raw_tasks)
        self.create_missing_projects(tasks, local)
        self.create_missing_users(tasks, local)
        self.create_missing_statuses(tasks, local)
        self.create_missing_types(tasks, local)
        self.create_missing_epics(tasks, local)
        self.create_missing_labels(tasks, local)
        self.create_missing_priorities(tasks, local)
        for task in tasks:
            self.mapping_task(local, task, response)
        return response

    def do_request(self, request_data, domain=[], paging=100, load_all=False):
        existing_record = self.env['work.task']
        headers = self.__get_request_headers()
        start_index = 0
        total_response = paging
        response = []
        local_data = self.get_local_task_data(domain)
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
            res = self.processing_task_raw_data(local_data, body)
            if res:
                existing_record |= res['updated']
            response.extend(res['new'])

        if existing_record:
            self.env.cr.execute(f"UPDATE work_task SET write_date = NOW() WHERE id IN %(ids)s",
                                {'ids': tuple(existing_record.ids)})
        return existing_record | self.env['work.task'].sudo().create(response)

    def load_tasks(self, extra_jql="", domain=[], load_all=False):
        request_data = {
            'endpoint': f"{self.work_host_url}/search",
            'params': [extra_jql]
        }
        tasks =  self.do_request(request_data, domain=domain, load_all=load_all)
        self.load_boards(tasks.mapped('project_id'))
        self.with_delay().update_board_by_new_tasks(self.env.user, tasks)

    def load_all_tasks(self):
        task_ids = self.load_tasks(load_all=True)
        if task_ids and self.import_work_log:
            for task_id in task_ids:
                self.with_delay().load_work_logs(task_id)

    def load_my_tasks(self):
        extra_jql = f"""jql=assignee='{self.env.user.partner_id.email}' ORDER BY createdDate ASC"""
        task_ids = self.load_tasks(extra_jql, domain=[('assignee_id', '=', self.env.user.id)], load_all=True)
        if task_ids and self.import_work_log:
            for task_id in task_ids:
                self.with_delay().load_work_logs(task_id)

    def load_by_links(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("work_base_integration.load_by_link_action_form")
        context = json.loads(action['context'])
        context.update({'default_host_id': self.id})
        action['context'] = context
        return action

    @api.model
    def search_task(self, keyword):
        return self.search_load(keyword)

    def _search_load(self, res, delay=False):
        task_ids = self.env['work.task']
        if 'task' in res:
            if not isinstance(res['task'], (list, tuple)):
                res['task'] = [res['task']]
            for key in res['task']:
                request_data = {
                    'endpoint': f"{self.work_host_url}/issue/{key.upper()}",
                }
                task_ids |= self.do_request(request_data,
                                             ['|', ('task_key', 'in', res['task']), ('epic_ok', '=', True)])
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
                'endpoint': f"{self.work_host_url}/search",
                "params": [query]
            }
            task_ids |= self.do_request(request_data, load_all=True)
        if delay:
            self.with_delay().load_work_logs(task_ids)
        else:
            self.load_work_logs(task_ids)

        self.load_boards(task_ids.mapped('project_id'))
        self.with_delay().update_board_by_new_tasks(self.env.user, task_ids)
        return task_ids

    def search_load(self, payload):
        res = get_search_request(payload)
        return self._search_load(res)

    # ===========================================  Section for loading work logs ===================================

    def get_local_worklog_data(self, task_id, domain):
        return {
            'dict_log': {x.id_onhost: x for x in task_id.time_log_ids if x.id_onhost},
            'dict_task': {task_id.work_id: task_id.id},
            'dict_task_to_log': {}
        }

    def prepare_worklog_data(self, local, log, task, response):
        user_id = local['dict_user'].get((log.author or log.author_accountId, self.company_id.id), False)
        if not user_id:
            _logger.info("MISSING ASSIGNEE: work.task(%ss)" %task.get(log.remote_task_id, False))
        curd_data = {
            'time': log.time,
            'duration': log.duration,
            'start_date': self.convert_host_tz_to_utc(log.start_date),
            'description': log.description or '',
            'id_onhost': log.remote_id,
            'capture_export_duration': log.duration,
            'capture_export_start_date': self.convert_host_tz_to_utc(log.start_date),
            'capture_export_description': log.description or '',
            'user_id': user_id,
            'state': 'done',
            'source': 'sync',
            'task_id': task.get(log.remote_task_id, False),
            'export_state': 1,
            'work_create_date': self.convert_host_tz_to_utc(log.create_date),
            'work_write_date': self.convert_host_tz_to_utc(log.write_date),
            'company_id': self.company_id.id
        }
        return curd_data

    def mapping_worklog(self, local, log, task, response):
        curd_data = self.prepare_worklog_data(local, log, task, response)
        if log.remote_id not in local['dict_log']:
            if log.duration > 0 and task.get(log.remote_task_id, False):
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
            mapping = ImportingJiraWorkLog(self.host_service, self.work_host_url)
        response = {
            'new': [],
            'updated': self.env['work.time.log']
        }
        raw_logs = raw.get('worklogs', [raw])
        logs = mapping.parse_logs(raw_logs)
        task = local['dict_task']
        self.create_missing_assignee(logs, local)
        for log in logs:
            self.mapping_worklog(local, log, task, response)
        return response

    def load_missing_work_logs_by_unix(self, unix, users, projects, batch=900, end_unix=-1):
        if self.import_work_log:
            for user in users:
                last_page = False
                mapping = ImportingJiraWorkLog(self.host_service, self.work_host_url)
                headers = self.with_user(user).__get_request_headers()
                task_ids = self.env['work.task'].search([('project_id', 'in', projects.ids)])
                local_data = {
                    'dict_log': {},
                    'dict_task': {task_id.work_id: task_id.id for task_id in task_ids},
                    'dict_user': self.with_context(active_test=False).get_user()
                }
                flush = set()
                to_create = []
                request_data = {
                    'endpoint': f"{self.work_host_url}/worklog/updated?since={unix}",
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
                                    SELECT ARRAY_AGG(id_onhost) AS result FROM work_time_log WHERE id_onhost IN %(ids)s AND project_id NOT IN %(project_ids)s
                                """, {
                                    'ids': tuple(flush),
                                    'project_ids': tuple(projects.ids)
                                })
                                res = self.env.cr.dictfetchone()
                                flush -= set(res['result'] or [])
                                if len(flush):
                                    request = {
                                        'endpoint': f"{self.work_host_url}/worklog/list",
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
                    self.env["work.time.log"].with_context(bypass_rounding=True).create(to_create)

    def load_work_logs_by_unix(self, unix, users, batch=900, end_unix=-1):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            for user in users:
                last_page = False
                mapping = ImportingJiraWorkLog(self.host_service, self.work_host_url)
                headers = self.with_user(user).__get_request_headers()
                task_ids = self.env['work.task'].search(
                    [('work_id', '!=', False), ('write_date', '>=', datetime.fromtimestamp(unix / 1000))])
                local_data = {
                    'dict_log': {x.id_onhost: x for x in task_ids.mapped('time_log_ids') if x.id_onhost},
                    'dict_task': {task_id.work_id: task_id.id for task_id in task_ids},
                    'dict_user': self.with_context(active_test=False).get_user()
                }
                flush = []
                to_create = []
                request_data = {
                    'endpoint': f"{self.work_host_url}/worklog/updated?since={unix}",
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
                                    'endpoint': f"{self.work_host_url}/worklog/list",
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
                    self.env["work.time.log"].create(to_create)

    def delete_work_logs_by_unix(self, unix, users, batch=900):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            for user in users:
                last_page = False
                headers = self.with_user(user).__get_request_headers()
                flush = []
                request_data = {
                    'endpoint': f"{self.work_host_url}/worklog/deleted?since={unix}",
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
                            self.env['work.time.log'].search([('id_onhost', 'in', flush)]).unlink()
                            flush = []
                        del body['values']
                    else:
                        _logger.warning(f"PAGE DELETED FAILED COUNT: {page_failed_count}")
                        page_failed_count += 1
                        time.sleep(30)
                        continue

    def load_work_logs(self, task_ids, paging=100, domain=[], load_all=False):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            mapping = ImportingJiraWorkLog(self.host_service, self.work_host_url)
            headers = self.__get_request_headers()
            user_dict = self.with_context(active_test=False).get_user()
            for task_id in task_ids:
                request_data = {
                    'endpoint': f"{self.work_host_url}/issue/{task_id.task_key}/worklog",
                }
                start_index = 0
                total_response = paging
                to_create = []
                local_data = self.get_local_worklog_data(task_id, domain)
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
                    new_tasks = self.with_context(force_delete=True).processing_worklog_raw_data(local_data, body,
                                                                                                  mapping)
                    to_create.extend(new_tasks.get('new'))
                if to_create:
                    self.env['work.time.log'].create(to_create)

    def load_work_log_by_ids_raw(self, ids, users):
        self = self.with_context(bypass_cross_user=True)
        if self.import_work_log:
            new_logs = []
            for user in users:
                mapping = ImportingJiraWorkLog(self.host_service, self.work_host_url)
                headers = self.with_user(user).__get_request_headers()
                local_data = {'dict_user': {}}
                request = {
                    'endpoint': f"{self.work_host_url}/worklog/list",
                    'method': 'post',
                    'body': {'ids': ids}
                }
                logs = self.make_request(request, headers)
                logs = mapping.parse_logs(logs)
                for log in logs:
                    new_logs.append(self.prepare_worklog_data(local_data, log, {}, {}))
                work_ids = list(map(lambda r: r['id_onhost'], new_logs))
                if set(ids) - set(work_ids):
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

    def add_time_logs(self, task_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/issue/{task_id.task_key}/worklog",
            'method': 'post',
        }
        for log in time_log_ids:
            payload = self._get_time_log_payload(log)
            request_data['body'] = payload
            # res = self.make_request(request_data, headers)
            log.id_onhost = res['id']
        time_log_ids.export_state = 1

    def update_time_logs(self, task_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/issue/{task_id.task_key}/worklog",
            'method': 'put',
        }
        for log in time_log_ids:
            try:
                payload = self._get_time_log_payload(log)
                request_data['body'] = payload
                request_clone = request_data.copy()
                request_clone['endpoint'] += f"/{log.id_onhost}"
                # res = self.make_request(request_clone, headers)
            except:
                continue
        time_log_ids.export_state = 1

    def delete_time_logs(self, task_id, time_log_ids):
        headers = self.__get_request_headers()
        request_data = {
            'endpoint': f"{self.work_host_url}/issue/{task_id.task_key}/worklog",
            'method': 'delete',
        }
        for log in time_log_ids:
            payload = self._get_time_log_payload(log)
            request_data['body'] = payload
            request_clone = request_data.copy()
            request_clone['endpoint'] += f"/{log.id_onhost}"
            # res = self.make_request(request_clone, headers)

    def export_specific_log(self, task_id, log_ids):
        time_log_to_create_ids = log_ids.filtered(lambda x: not x.id_onhost and x.state == 'done')
        time_log_to_update_ids = log_ids.filtered(lambda x: x.id_onhost and x.state == 'done')
        self.add_time_logs(task_id, time_log_to_create_ids)
        self.update_time_logs(task_id, time_log_to_update_ids)

    def export_time_log(self, task_id):
        current_user_id = self.env.user.id
        time_log_to_create_ids = task_id.time_log_ids.filtered(lambda x: not x.id_onhost and x.state == 'done')
        time_log_to_update_ids = task_id.time_log_ids.filtered(
            lambda x: x.id_onhost
                      and (not task_id.last_export or x.write_date > task_id.last_export)
                      and (x.user_id.id == current_user_id)
                      and x.state == 'done'
        )
        self.add_time_logs(task_id, time_log_to_create_ids)
        self.update_time_logs(task_id, time_log_to_update_ids)

    def _update_project(self, project_id, project_last_update):
        self = self.with_context(bypass_cross_user=True)
        updated_date = datetime(1970, 1, 1, 1, 1, 1, 1)
        if project_last_update:
            updated_date = self.convert_utc_to_usertz(project_last_update)
        str_updated_date = updated_date.strftime('%Y-%m-%d %H:%M')
        params = f"""jql=project="{project_id.project_key}" AND updated >= '{str_updated_date}'"""
        request_data = {'endpoint': f"{self.work_host_url}/search", "params": [params]}
        task_ids = self.do_request(request_data, load_all=True)
        _logger.info(f"{project_id.project_name}: {len(task_ids)}")

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
            request_data = {'endpoint': f"{self.work_host_url}/search", "params": [params]}

            task_ids = self.do_request(request_data, load_all=True)

            _logger.info(f"Batch Load Of User {user.display_name}: {len(task_ids)}")
            self.load_boards(projects)
            self.with_delay().update_board_by_new_tasks(user_id, task_ids)

    def load_boards(self, project_ids=False):
        self.ensure_one()
        if not self.work_agile_url:
            return
        if not project_ids:
            project_ids = self.env["work.project"].sudo().search([])
        project_by_key = {project.project_key: project for project in project_ids}
        existed_boards = set(project_ids.mapped('board_ids').mapped('id_onhost'))
        allowed_user_ids = self.admin_user_ids
        if self.is_round_robin:
            allowed_user_ids = project_ids.mapped('allowed_manager_ids')
        allowed_user_ids = allowed_user_ids.token_exists_by_host(self)
        if not allowed_user_ids:
            return
        for user in allowed_user_ids:
            headers =  self.with_user(user).__get_request_headers()
            request_data = {
                'endpoint': f"""{self.work_agile_url}/board""",
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
                                'id_onhost': board['id'],
                                'name': board['name'],
                                'type': board['type'],
                                'project_id': project.id,
                            })
        self.env.user.token_clear_cache()

    def prepare_local_agile(self):
        company_id = self.company_id.id
        return {
            'sprints': {x.id_onhost: x for x in self.env['agile.sprint'].sudo().search([('company_id', '=', company_id)])},
            'boards': {x.id_onhost: x for x in self.env['board.board'].sudo().search([('company_id', '=', company_id)])},
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
                        'id_onhost': sprint['id'],
                        'name': sprint['name'],
                        'state': sprint['state'],
                        'project_id': existing_board.project_id.id,
                        'board_id': existing_board.id,
                        'updated': True
                    })
                    local['sprints'][sprint.id_onhost] = sprint
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
            'endpoint': f"""{self.work_agile_url}/board/{board.id_onhost}/sprint?maxResults=50""",
            'method': 'get',
        }
        try:
            data = self.make_request(request_data, headers)
            self._map_sprint_values(data.get('values') or [], local)
        except Exception as e:
            error_str = traceback.format_exc()
            error_str += "\n %s"%board
            board.active = False
            raise Exception(error_str)

    def __get_sprint_by_id(self, sprint_id, local):
        try:
            headers = self.__get_request_headers()
            request_data = {
                'endpoint': f"""{self.work_agile_url}/sprint/{sprint_id}""",
                'method': 'get',
            }
            data = self.make_request(request_data, headers)
            self._map_sprint_values([data], local)
        except Exception as e:
            sprint_id.active = False
            raise e

    def update_task_for_sprints(self, sprint_ids=False):
        if not sprint_ids:
            sprint_ids = self.env["agile.sprint"].sudo().search([])
        sprint_by_id = {sprint.id_onhost: sprint for sprint in sprint_ids}
        tasks = self.env['work.task'].sudo().search([('sprint_key', 'in', sprint_ids.mapped('id_onhost'))])
        for task in tasks:
            task.write({'sprint_id': sprint_by_id[task.sprint_key], 'sprint_key': False})

    def update_board_by_new_tasks(self, user, tasks):
        local = self.prepare_local_agile()
        existing_sprints = tasks.mapped('sprint_id')
        existing_boards = existing_sprints.mapped('board_id')
        self = self.with_user(user)
        for board in existing_boards:
            self.with_context(board=board).__get_sprints_by_board(board, local)

        new_sprint_ids = tasks.filtered('sprint_key').mapped('sprint_key')
        existing_sprint_ids = self.env['board.board'].sudo().search([('id_onhost', 'in', new_sprint_ids)]).ids
        gap_sprint_ids = set(new_sprint_ids) - set(existing_sprint_ids)
        if gap_sprint_ids:
            for sprint_id in gap_sprint_ids:
                self.__get_sprint_by_id(sprint_id, local)

        sprints = self.env['agile.sprint'].sudo().search([('id_onhost', 'in', new_sprint_ids)])
        self.update_task_for_sprints(sprints)

    # Agile Connection

    def load_sprints(self, board_ids=False):
        self.ensure_one()
        if not self.work_agile_url:
            return
        if not board_ids:
            board_ids = self.env['board.board'].sudo().search([])
        allowed_user_ids = self.admin_user_ids
        if self.is_round_robin:
            allowed_user_ids = self.env['res.users'].search([])
        allowed_user_ids = allowed_user_ids.token_exists_by_host(self)
        header_by_user = dict()
        board_ids = board_ids.filtered(lambda r: r.type == "scrum")
        local = self.prepare_local_agile()
        for board in board_ids:
            try:
                if not board.id_onhost and not board.type == 'scrum':
                    continue
                usable_user = (board.project_id.allowed_manager_ids & allowed_user_ids)
                if not usable_user:
                    continue
                headers = header_by_user.get(usable_user[0]) or self.with_user(usable_user[0]).__get_request_headers()
                if usable_user[0] not in header_by_user:
                    header_by_user[usable_user[0]] = headers
                request_data = {
                    'endpoint': f"""{self.work_agile_url}/board/{board.id_onhost}/sprint?maxResults=50""",
                    'method': 'get',
                }
                data = self.make_request(request_data, headers)
                self.with_context(board=board)._map_sprint_values(data.get('values') or [], local)
            except Exception as e:
                _logger.error(e)

        self.env.user.token_clear_cache()
