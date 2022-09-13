from odoo import api, fields, models, _
from datetime import datetime
import time
import logging

_logger = logging.getLogger(__name__)


class WtProject(models.Model):
    _inherit = "wt.project"

    wt_migration_id = fields.Many2one("wt.migration", string="Task Migration Credentials")
    last_update = fields.Datetime("Last Update Cron")
    allow_to_fetch = fields.Boolean("Should Fetch?")
 
    @api.model
    def cron_fetch_issue(self, load_create=True):
        if not self:
            self = self.search([('allow_to_fetch', '=', True), ('wt_migration_id.active', '=', True)])
        latest_unix = int(self.env['ir.config_parameter'].get_param('latest_unix'))
        checkpoint_unix = datetime.now()
        allowed_user_ids = self.env['res.users'].search([]).token_exists()
        migration_dict = dict()
        for project in self:
            if project.wt_migration_id not in migration_dict:
                migration_dict[project.wt_migration_id] = self.env['res.users']
            if project.allowed_user_ids:
                user_ids = allowed_user_ids & project.allowed_user_ids
                if not (user_ids & migration_dict[project.wt_migration_id]) and user_ids:
                    migration_dict[project.wt_migration_id] |= user_ids[0]
                if len(user_ids) == 0 and project.wt_migration_id:
                    user_ids = project.wt_migration_id.admin_user_ids.ids
                if project.last_update and project.last_update.timestamp() * 1000 < latest_unix and user_ids and project.wt_migration_id:
                    project.wt_migration_id.update_project(project, user_ids[0])
                project.last_update = checkpoint_unix

        for wt in migration_dict.keys():
            wt.with_delay().update_projects(latest_unix, migration_dict[wt])
            wt.with_delay(eta=1).delete_work_logs_by_unix(latest_unix, migration_dict[wt])
            wt.with_delay(eta=2).load_work_logs_by_unix(latest_unix, migration_dict[wt])
        
        self.env['ir.config_parameter'].set_param('latest_unix', int(checkpoint_unix.timestamp() * 1000))

    def reset_state(self):
        for record in self:
            record.last_update = False
