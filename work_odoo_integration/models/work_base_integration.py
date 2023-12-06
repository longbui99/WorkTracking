
import logging
import xmlrpc.client
from functools import reduce
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from odoo import models, api, fields, _

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class OdooHost(models.Model):
    _inherit = "work.base.integration"

    host_type = fields.Selection(selection_add=[
        ('odoo', 'Odoo Timesheet')
    ], ondelete={'odoo': lambda recs: recs.write({'host_type': 'odoo_inactive'})})
    database = fields.Char(string="Database")

    @api.model
    def generate_record_by_key(self, datas, key):
        dictionary = dict()
        for record in datas:
            dictionary[record[key]] = record
        return dictionary

    @api.model
    def merge_odoo_credential(self, login, password):
        return f"{login}::{password}"

    @api.model
    def split_odoo_credential(self, token):
        return token.split("::")
    
    @api.model
    def parse_name_to_key(self, name):
        names = name.split(' ')
        res = ""
        count = 0
        for segment in names:
            if segment.strip().isalnum():
                res += segment[0].upper()
                count +=1
                if count == 3:
                    break
        return "O" + res

    def make_rpc_agent(self):
        self.ensure_one()
        if self.env.context.get('rpc'):
            return self.env.context.get('rpc')
        user = self.env.user
        host_private_key = user.get_token(self)
        login, password = self.split_odoo_credential(host_private_key)
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.base_url))
        uid = common.authenticate(self.database, login, password, {})
        model = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.base_url))
        def env(*args):
            return model.execute_kw(self.database, uid, password, *args)
        return env
    
    def load_projects(self):
        if self.host_type == "odoo":
            gather_project_ids = self._context.get('gather_project_ids')
            domain = []
            if gather_project_ids:
                domain = [('id', 'in', gather_project_ids)]
            forced_project_domain = self._context.get('forced_project_domain') or []
            domain += forced_project_domain
            projects = self.env['work.project']
            rpc = self.make_rpc_agent()
            project_datas = rpc('project.project', 'search_read', [
                domain,# Domain
                ['name']
            ])
            id_list = [project_data['id'] for project_data in project_datas]
            project_external_ids = set(self.env['work.project'].search([('external_id', 'in', id_list), ('host_id','=', self.id)]).mapped('external_id'))
            value_list = []
            user_id = self.env.user
            for project_data in project_datas:
                if project_data['id'] not in project_external_ids:
                    key = self.parse_name_to_key(project_data['name'])
                    res = {
                        'project_name': project_data['name'],
                        'project_key': key,
                        'host_id': self.id,
                        'allow_to_fetch': True,
                        'external_id': project_data['id'],
                        'company_id': self.company_id.id,
                    }
                    if user_id:
                        res['allowed_manager_ids'] = [(4, user_id.id, False)]
                    value_list.append(res)
            projects |= projects.sudo().create(value_list)
            return projects
        else:
            return super().load_projects()
        
    def load_all_users(self, user_email=''):
        if self.host_type == "odoo":
            gather_user_ids = self._context.get('gather_user_ids')
            domain = []
            if gather_user_ids:
                domain = [('id', 'in', gather_user_ids)]
            forced_user_domain = self._context.get('forced_user_domain') or []
            domain += forced_user_domain
            users = self.env['res.users']
            UserEnv = self.env['res.users'].sudo()
            rpc = self.make_rpc_agent()
            user_datas = rpc('res.users', 'search_read', [
                domain,# Domain
                ['name', 'email', 'tz']
            ])
            emails = [user['email'] for user in user_datas]
            user_emails = set(self.env['res.users'].with_context(active_test=False).\
                              search(['|', ('login', 'in', emails), ('email', 'in', emails)]).mapped('email'))
            for user_data in user_datas:
                if user_data['email'] not in user_emails:
                    new_user = UserEnv.create({
                        "name": user_data["name"],
                        "login": user_data['email'],
                        'email': user_data['email'],
                        'company_id': self.company_id.id,
                        'company_ids': [(6, 0, self.company_id.ids)],
                        'tz': user_data['tz'],
                        'account_id': user_data['id']
                    })
                    new_user.action_create_employee()
                    users |= new_user
            users.write({'active': False})
            return users
        else:
            return super().load_all_users(user_email)
    
    def _check_missing_users(self, user_ids):
        users = self.env['res.users'].search([('account_id', 'in', user_ids)])
        user_ids = set(user_ids) - set(users.mapped('account_id'))
        if user_ids:
            return self.load_all_users()
        return True

    def load_all_tasks(self):
        if self.host_type == "odoo":
            gather_task_ids = self._context.get('gather_task_ids')
            domain = []
            if gather_task_ids:
                domain = [('id', 'in', gather_task_ids)]
            forced_task_domain = self._context.get('forced_task_domain') or []
            domain += forced_task_domain
            task_env = self.env['work.task'].sudo()
            rpc = self.make_rpc_agent()
            task_datas = rpc('project.task', 'search_read', [
                domain,# Domain
                ['name', 'project_id', 'user_ids']
            ])
            ids = list(map(lambda task: task['id'], task_datas))
            tasks = self.env['work.task'].search([
                ('host_id', '=', self.id),
                ('host_id', 'in', ids)
            ])
            task_ids = set(tasks.mapped('id_onhost'))
            user_ids = [j for sub in list(map(lambda r: r['user_ids'], task_datas)) for j in sub]
            self._check_missing_users(user_ids)
            user_emails = rpc('res.users', 'search_read', [[('id', 'in', user_ids)], ['login']])
            local_user_by_email = self.generate_record_by_key(self.env['res.users'].with_context(active_test=False).search([]), 'login')
            local_project_by_id = self.generate_record_by_key(self.env['work.project'].search([('host_id', '=', self.id)]), 'external_id')
            external_user_by_id = self.generate_record_by_key(user_emails, 'id')
            
            to_fetch_projects = []
            for task_data in task_datas:
                ex_project_id = task_data['project_id'] and task_data['project_id'][0] or False
                if ex_project_id and str(ex_project_id) not in local_project_by_id:
                    to_fetch_projects.append(ex_project_id)

            if len(to_fetch_projects):
                projects = self.with_context(gather_project_ids=to_fetch_projects).load_projects()
                extend_projects = self.generate_record_by_key(projects, 'external_id')
                local_project_by_id.update(extend_projects)

            value_list = []
            for task_data in task_datas:
                if task_data['id'] not in task_ids:
                    ex_project_id = task_data['project_id'] and task_data['project_id'][0] or False
                    project = local_project_by_id.get(str(ex_project_id))
                    project_id = project and project.id or False
                    project_key = project and project.project_key or "NaN"

                    assignee_id = False
                    ex_user_ids = task_data['user_ids']
                    if ex_user_ids:
                        assignee = local_user_by_email.get(external_user_by_id.get(ex_user_ids[0], {}).get('login', False))
                        if assignee:
                            assignee_id = assignee.id
                    value_list.append({
                        'task_name': task_data['name'],
                        'project_id': project_id,
                        'task_key': f"{project_key}-{task_data['id']}",
                        'assignee_id': assignee_id,
                        'host_id': task_data['id'],
                        'host_id': self.id,
                        'task_url': self.base_task_url%task_data['id']
                    })
            tasks = tasks | task_env.create(value_list)
            if self.import_work_log:
                self.with_context(bypass_cross_user=True).load_work_logs(tasks)
            return tasks
        else:
            return super().load_all_tasks()
        
    def _update_project(self, project_id, project_last_update):
        if self.host_type == "odoo":
            self = self.with_context(bypass_cross_user=True)
            updated_date = datetime(1970, 1, 1, 1, 1, 1, 1)
            if project_last_update:
                updated_date = project_last_update
            str_updated_date = updated_date.strftime('%Y-%m-%d %H:%M')
            domain = [('project_id', '=', int(project_id.external_id)), ('write_date', '>=', str_updated_date)]
            task_ids = self.with_context(forced_task_domain=domain).load_all_tasks()
            _logger.info(f"{project_id.project_name}: {len(task_ids)}")
        else:
            return super()._update_project(project_id, project_last_update)

    def load_logs_by_unix(self, unix):
            self = self.with_context(bypass_cross_user=True)
            str_updated_date = datetime.fromtimestamp(unix / 1000).strftime('%Y-%m-%d %H:%M')
            gather_logs_ids = self._context.get('gather_logs_ids')
            domain = [('user_id', '!=', False), ('task_id', '!=', False)]
            if gather_logs_ids:
                domain += [('id', 'in', gather_logs_ids)]
            forced_log_domain = self._context.get('forced_log_domain') or []
            domain += forced_log_domain
            domain += [('write_date', '>=', str_updated_date)]
            rpc = self.make_rpc_agent()
            log_datas = rpc('account.analytic.line', 'search_read', [
                domain,
                ['date', 'user_id', 'name', 'project_id', 'task_id', 'unit_amount', 'create_date', 'write_date']
            ])
            ids = list(map(lambda log: log['id'], log_datas))
            logs = self.env['work.time.log'].with_context(active_test=False).\
                            search([('id_onhost', 'in', ids)])
            log_by_id = self.generate_record_by_key(logs, 'id_onhost')
            user_ids = list(map(lambda log: log['user_id'][0], log_datas))
            user_emails = rpc('res.users', 'search_read', [[('id', 'in', user_ids)], ['login']])
            local_user_by_email = self.generate_record_by_key(self.env['res.users'].with_context(active_test=False).search([]), 'login')
            external_user_by_id = self.generate_record_by_key(user_emails, 'id')
            task_by_in_onhost = self.generate_record_by_key(self.env['work.task'].with_context(active_test=False).search([('host_id', '=', self.id)]), 'id_onhost')
            to_fetch_tasks = []
            for log in log_datas:
                task_id = False
                task = task_by_in_onhost.get(log['task_id'][0])
                if not task:
                    to_fetch_tasks.append(log['task_id'][0])

            if to_fetch_tasks:
                tasks = self.with_context(gather_task_ids=to_fetch_tasks).load_all_tasks()
                concat_task_by_in_onhost = self.generate_record_by_key(tasks, 'id_onhost')
                task_by_in_onhost.update(concat_task_by_in_onhost)

            value_list = []
            for log in log_datas:
                if log['id'] not in log_by_id:
                    company_id = self.company_id.id
                    task_id = False
                    task = task_by_in_onhost.get(log['task_id'][0])
                    if not task:
                        raise UserError("Cannot find task for %s"%str(log))
                    else:
                        task_id = task.id
                        company_id = task.company_id.id

                    assignee_id = False
                    ex_user_ids = log['user_id']
                    if ex_user_ids:
                        assignee = local_user_by_email.get(external_user_by_id.get(ex_user_ids[0], {}).get('login', False))
                        if assignee:
                            assignee_id = assignee.id
                    value_list.append({
                        'user_id': assignee_id,
                        'description': log['name'],
                        'duration': log['unit_amount']*3600,
                        'task_id': task_id,
                        'start_date': log['date'],
                        'export_state': 1,
                        'id_onhost': log['id'],
                        'host_create_date': log['create_date'],
                        'host_write_date': log['write_date'],
                        'company_id': company_id,
                        'state': 'done'
                    })
                else:
                    odoo_log = log_by_id[log['id']]
                    vals = {}
                    if odoo_log.duration_hrs != log['unit_amount']:
                        vals['duration'] = 3600*log['unit_amount']
                    if odoo_log.start_date.date != log['date']:
                        vals['start_date'] = log['date']
                    if odoo_log.description != log['name']:
                        vals['description'] = log['name']
                    vals['export_state'] = 1
                    odoo_log.update(vals)
            return self.env['work.time.log'].sudo().create(value_list)

    def load_missing_work_logs_by_unix(self, unix, users, projects, batch=900, end_unix=-1):
        if self.host_type == "odoo":
            res = self.env['work.time.log']
            for user in users:
                user_self = self.with_user(user)
                domain = []
                res |= user_self.with_context(forced_log_domain=domain).load_logs_by_unix(unix)
            return res
        else:
            return super().load_missing_work_logs_by_unix(unix, users, projects, batch, end_unix)

    def update_projects(self, latest_unix, project_by_user_id):
        if self.host_type == "odoo":
            self = self.with_context(bypass_cross_user=True)
            for user_id, projects in project_by_user_id.items():
                user = self.env['res.users'].browse(int(user_id)).exists()
                self = self.with_user(user)
                str_updated_date = datetime.fromtimestamp(latest_unix / 1000).strftime('%Y-%m-%d %H:%M')
                domain = [('project_id', '=', list(map(int, projects.mapped('external_id')))), ('write_date', '>=', str_updated_date)]
                task_ids = self.with_context(forced_task_domain=domain).load_all_tasks()
                _logger.info(f"Batch Load Of User {user.display_name}: {len(task_ids)}")
        else:
            return super().update_projects(latest_unix, project_by_user_id)
    
    def delete_work_logs_by_unix(self, unix, users, batch=900):
        if self.host_type == "odoo":
            return
        else:
            super().delete_work_logs_by_unix(unix, users, batch)

    def load_work_logs_by_unix(self, unix, users, batch=900):
        if self.host_type == "odoo":
            res = self.env['work.time.log']
            if self.import_work_log:
                self = self.with_context(bypass_cross_user=True)
                project_ids = list(map(int,self.env['work.project'].search([('host_id', 'in', self.ids)]).mapped('external_id')))
                tasks = self.env['work.task'].search([('host_id', 'in', self.ids)])
                task_ids = tasks.mapped('id_onhost')
                local_logs = tasks.mapped('time_log_ids').filtered(lambda r: r.export_state != 0)
                local_log_ex_ids = set(local_logs.mapped('id_onhost'))
                log_data_set = set()
                for user in users:
                    user_self = self.with_user(user)
                    rpc = user_self.make_rpc_agent()
                    log_data_ids = rpc('account.analytic.line', 'search', [['|', ('project_id', 'in', project_ids), ('task_id', 'in', task_ids)]])
                    log_data_set.update(log_data_ids)
                    add_ids = set(log_data_ids) - local_log_ex_ids
                    if add_ids:
                        res |= user_self.with_context(rpc=rpc).load_logs_by_unix(unix)
                to_delete_ex_ids = local_log_ex_ids - log_data_set
                if to_delete_ex_ids:
                    self.env['work.time.log'].search([('id_onhost', 'in', list(to_delete_ex_ids)), ('task_id.host_id', 'in', self.ids)]).unlink()
            return res
        else:
            return super().load_work_logs_by_unix(unix, users, batch)
    
    def load_work_logs(self, task_ids, paging=100, domain=[], load_all=False):
        if self.host_type == "odoo":
            domain = [('task_id', 'in', task_ids.mapped('id_onhost'))]
            res = self.with_context(forced_log_domain=domain).load_logs_by_unix(0)
            return res
        else:
            return super().load_work_logs(task_ids, paging, domain, load_all)

    def _fetch_odoo_task_by_endpoint(self, endpoint):
        self.ensure_one()
        params = parse_qs(urlparse(endpoint.replace("#", "?")).query)
        task_id = 0
        if params.get('model') and params['model'][0] == "project.task" and params.get('id') and params['id'][0]:
            task_id = int(params['id'][0])
        return task_id

    def _search_load(self, res, delay=False):
        if self.host_type == "odoo":
            task_ids = self.env['work.task']
            if 'task' in res:
                if not isinstance(res['task'], list):
                    res['task'] = [res['task']]
                task_ids = []
                for task in res['task']:
                    if isinstance(task, str):
                        params = task.split('-')
                        if len(params) == 2:
                            task_ids.append(int(params[1]))
                    elif isinstance(task, int):
                        task_ids.append(task)
                domain = [('id', 'in', task_ids)]
            else:
                domain = []
                if 'project' in res:
                    domain += [('project_id', 'in', res['project'])]
                if "mine" in res:
                    domain += [('user_ids.login', '=', self.env.user.login)]
                if "text" in res:
                    domain += [('name', 'ilike', f"%{res['text']}%")]
            task_ids = self.with_context(forced_task_domain=domain).load_all_tasks()
            if delay:
                self.with_delay().load_work_logs(task_ids)
            else:
                self.load_work_logs(task_ids)
            return task_ids
        else:
            return super()._search_load(res, delay)

    @api.model
    def _prepare_odoo_timesheet_log_vals(self, log):
        return {
            'date': log.start_date.strftime('%Y-%m-%d'),
            'name': log.description,
            'unit_amount': log.duration_hrs,
            'task_id': log.task_id.host_id
        }

    def export_specific_log(self, task_id, log_ids):
        if self.host_type == "odoo":
            rpc = self.make_rpc_agent()
            self = self.with_context(rpc=rpc)
        return super().export_specific_log(task_id, log_ids)

    def add_time_logs(self, task_id, time_log_ids):
        if self.host_type == "odoo":
            if time_log_ids:
                rpc = self.make_rpc_agent()
                val_list = [self._prepare_odoo_timesheet_log_vals(log) for log in time_log_ids]
                res = rpc('account.analytic.line', 'create', [val_list])
                for log, ex_id in zip(time_log_ids, res):
                    log['id_onhost'] = ex_id
                return res
        else:
            return super().add_time_logs(task_id, time_log_ids)

    def update_time_logs(self, task_id, time_log_ids):
        if self.host_type == "odoo":
            if time_log_ids:
                rpc = self.make_rpc_agent()
                for log in time_log_ids:
                    vals = self._prepare_odoo_timesheet_log_vals(log)
                    rpc('account.analytic.line', 'write', [log.id_onhost, vals])
        else:
            return super().update_time_logs(task_id, time_log_ids)

    def delete_time_logs(self, task_id, time_log_ids):
        if self.host_type == "odoo":
            if time_log_ids:
                rpc = self.make_rpc_agent()
                rpc('account.analytic.line', 'unlink', [time_log_ids.mapped('id_onhost')])
        else:
            return super().delete_time_logs(task_id, time_log_ids)

    def load_initial_projects(self):
        res = super().load_initial_projects()
        if self.host_type == "odoo":
            self._search_load({'all': []})
        return res
