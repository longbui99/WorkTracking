from odoo import api, fields, models, _
from datetime import datetime
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


class WorkProject(models.Model):
    _inherit = "work.project"

    host_id = fields.Many2one("work.base.integration", string="Task Host Credentials", ondelete="cascade")
    last_update = fields.Datetime("Last Update Cron")
    allow_to_fetch = fields.Boolean("Should Fetch?")
    external_id = fields.Char(string="External ID")
 
    @api.model
    def cron_fetch_task(self, load_create=True):
        if not self:
            self = self.search([('allow_to_fetch', '=', True), ('host_id.active', '=', True)])
        latest_unix = int(self.env['ir.config_parameter'].sudo().get_param('latest_unix'))
        checkpoint_unix = datetime.now()
        doable_user_ids = self.mapped('allowed_manager_ids') | self.mapped('allowed_user_ids')
        token_user_by_host = defaultdict(lambda: self.env['res.users'])

        hosts = self.mapped('host_id')
        for host in hosts:
            token_user_by_host[host] = doable_user_ids.token_exists_by_host(host)

        new_projects_by_user = defaultdict(lambda: self.env['work.project'])
        project_by_host = defaultdict(lambda: self.env['work.project'])
        for project in self:
            if project.host_id:
                project_by_host[project.host_id] |= project

        project_by_user_by_host = defaultdict(lambda: defaultdict(lambda: self.env['work.project']))
        user_by_host = defaultdict(set)

        for host, projects in project_by_host.items():
            allowed_user_ids = token_user_by_host[host]
            if allowed_user_ids:
                for project in projects:
                    user_ids = []
                    if not project.host_id.is_round_robin and project.host_id.admin_user_ids:
                        user_ids = allowed_user_ids & project.host_id.admin_user_ids
                    elif project.allowed_manager_ids or not project.host_id.full_sync:
                        user_ids = allowed_user_ids & project.allowed_manager_ids
                    elif project.allowed_user_ids:
                        user_ids = allowed_user_ids & project.allowed_user_ids

                    if not (user_ids):
                        continue
                    applicable_users = user_ids
                    if not host.full_sync:
                        applicable_users = user_ids[0]
                        for user in user_ids:
                            if user in user_by_host[host]:
                                applicable_users = user
                                break
                        user_by_host[host].add(applicable_users)

                    if not project.last_update and applicable_users and project.host_id:
                        for user in applicable_users:
                            new_projects_by_user[user] |= project
                    else:
                        for user in applicable_users:
                            project_by_user_by_host[host][user.id] |= project

        if new_projects_by_user:
            for user, projects in new_projects_by_user.items():
                projects.with_user(user).load_new_project()

        if len(project_by_user_by_host.keys()):
            for host, project_by_user in project_by_user_by_host.items():
                host.with_delay().update_projects(latest_unix, project_by_user)
                if host.import_work_log:
                    users = self.env['res.users'].browse((project_by_user.keys()))
                    host.with_delay(eta=1).delete_work_logs_by_unix(latest_unix, users)
                    host.with_delay(eta=2).load_work_logs_by_unix(latest_unix, users)
        
        self.sudo().write({'last_update': checkpoint_unix})
        self.env['ir.config_parameter'].sudo().set_param('latest_unix', int(checkpoint_unix.timestamp() * 1000))

    def load_new_project(self):
        host_dict = defaultdict(lambda: self.env['work.project'])
        for new_project in self:
            host_dict[new_project.host_id] |= new_project
        last_updated = datetime.now()
        for host_id, projects in host_dict.items():
            for project in projects:
                host_id.with_delay()._update_project(project, project.last_update)
            if host_id.import_work_log:
                host_id.with_delay(eta=1).load_missing_work_logs_by_unix(0, self.env.user, projects)
            projects.sudo().last_update = last_updated

    def reset_state(self):
        for record in self:
            record.last_update = False

    @api.model_create_multi
    def create(self, value_list):
        res = super().create(value_list)
        _logger.info("NEW PROJECT: %s" % res.mapped('project_key'))
        res.load_new_project()
        return res
