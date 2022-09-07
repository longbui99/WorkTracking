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
        allowed_user_ids = self.env['hr.employee'].search([('wt_private_key', '!=', False)], order='is_wt_admin desc').mapped('user_id')
        migration_dict = dict()
        for project in self:
            if project.wt_migration_id not in migration_dict:
                migration_dict[project.wt_migration_id] = self.env['res.users']
            if project.allowed_user_ids:
                user_ids = allowed_user_ids & project.allowed_user_ids
                if not (user_ids & migration_dict[project.wt_migration_id]):
                    migration_dict[project.wt_migration_id] |= user_ids[0]
                if len(user_ids) == 0 and project.wt_migration_id:
                    user_ids = project.wt_migration_id.admin_user_ids.ids
                employee_id = self.env['hr.employee'].search(
                    [('user_id', 'in', user_ids.ids),
                    ('wt_private_key', '!=', False)], order='is_wt_admin desc', limit=1)
                _logger.info(project.last_update.timestamp() * 1000)
                if project.last_update.timestamp() * 1000 < latest_unix and any(employee_id) and project.wt_migration_id:
                    project.wt_migration_id.update_project(project, employee_id)

        for wt in migration_dict.keys():
            employee_ids = self.env['hr.employee'].search(
                    [('user_id', 'in', migration_dict[wt].ids),
                    ('wt_private_key', '!=', False)], order='is_wt_admin desc')
            wt.with_delay().update_projects(latest_unix, employee_ids)
            wt.with_delay(eta=1).delete_work_logs_by_unix(latest_unix, employee_ids)
            wt.with_delay(eta=2).load_work_logs_by_unix(latest_unix, employee_ids)
        
        self.env['ir.config_parameter'].set_param('latest_unix', int(datetime.now().timestamp() * 1000))

    def reset_state(self):
        for record in self:
            record.last_update = False
