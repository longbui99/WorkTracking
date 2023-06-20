from odoo import api, fields, models, _
from datetime import datetime
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


class WtProject(models.Model):
    _inherit = "wt.project"

    wt_migration_id = fields.Many2one("wt.migration", string="Task Migration Credentials", ondelete="cascade")
    last_update = fields.Datetime("Last Update Cron")
    allow_to_fetch = fields.Boolean("Should Fetch?")
    external_id = fields.Char(string="External ID")
 
    @api.model
    def cron_fetch_issue(self, load_create=True):
        if not self:
            self = self.search([('allow_to_fetch', '=', True), ('wt_migration_id.active', '=', True)])
        latest_unix = int(self.env['ir.config_parameter'].sudo().get_param('latest_unix'))
        checkpoint_unix = datetime.now()
        doable_user_ids = self.mapped('allowed_manager_ids') | self.mapped('allowed_user_ids')
        token_user_by_migration = defaultdict(lambda: self.env['res.users'])

        migrations = self.mapped('wt_migration_id')
        for migration in migrations:
            token_user_by_migration[migration] = doable_user_ids.token_exists_by_migration(migration)

        new_projects_by_user = defaultdict(lambda: self.env['wt.project'])
        project_by_migration = defaultdict(lambda: self.env['wt.project'])
        for project in self:
            if project.wt_migration_id:
                project_by_migration[project.wt_migration_id] |= project

        project_by_user_by_migration = defaultdict(lambda: defaultdict(lambda: self.env['wt.project']))
        user_by_migration = defaultdict(set)

        for migration, projects in project_by_migration.items():
            allowed_user_ids = token_user_by_migration[migration]
            if allowed_user_ids:
                for project in projects:
                    user_ids = []
                    if not project.wt_migration_id.is_round_robin and project.wt_migration_id.admin_user_ids:
                        user_ids = allowed_user_ids & project.wt_migration_id.admin_user_ids
                    elif project.allowed_manager_ids:
                        user_ids = allowed_user_ids & project.allowed_manager_ids
                    elif project.allowed_user_ids:
                        user_ids = allowed_user_ids & project.allowed_user_ids
                    
                    if not len(user_ids):
                        continue
                    applicable_user = user_ids[0]
                    for user in user_ids:
                        if user in  user_by_migration[migration]:
                            applicable_user = user
                            break
                    user_by_migration[migration].add(applicable_user)
                    if not project.last_update and applicable_user and project.wt_migration_id:
                        new_projects_by_user[applicable_user] |= project
                    else:
                        project_by_user_by_migration[migration][applicable_user.id] |= project

        
        if new_projects_by_user:
            for user, projects in new_projects_by_user.items():
                projects.with_user(user).load_new_project()
        if len(project_by_user_by_migration.keys()):
            for migration, project_by_user in project_by_user_by_migration.items():
                migration.with_delay().update_projects(latest_unix, project_by_user)
                if migration.import_work_log:
                    users = self.env['res.users'].browse((project_by_user.keys()))
                    migration.with_delay(eta=1).delete_work_logs_by_unix(latest_unix, users)
                    migration.with_delay(eta=2).load_work_logs_by_unix(latest_unix, users)
        
        self.sudo().write({'last_update': checkpoint_unix})
        self.env['ir.config_parameter'].sudo().set_param('latest_unix', int(checkpoint_unix.timestamp() * 1000))

    def load_new_project(self):
        migration_dict = defaultdict(lambda: self.env['wt.project'])
        for new_project in self:
            migration_dict[new_project.wt_migration_id] |= new_project
        last_updated = datetime.now()
        for migration_id, projects in migration_dict.items():
            for project in projects:
                migration_id.with_delay()._update_project(project, project.last_update)
            if migration_id.import_work_log:
                migration_id.with_delay(eta=1).load_missing_work_logs_by_unix(0, self.env.user, projects)
            projects.sudo().last_update = last_updated

    def reset_state(self):
        for record in self:
            record.last_update = False

    @api.model_create_multi
    def create(self, value_list):
        res = super().create(value_list)
        _logger.info("NEW PROJECT: %s" % res.mapped('project_key'))
        return res
