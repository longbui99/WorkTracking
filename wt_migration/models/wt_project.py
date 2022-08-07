from odoo import api, fields, models, _
from datetime import datetime
import time


class JiraProject(models.Model):
    _inherit = "wt.project"

    wt_migration_id = fields.Many2one("wt.migration", string="Task Migration Credentials")
    last_update = fields.Datetime("Last Update Cron")
    allow_to_fetch = fields.Boolean("Should Fetch?")

    @api.model
    def cron_fetch_issue(self, load_create=True):
        if not self:
            self = self.search([('allow_to_fetch', '=', True), ('wt_migration_id.active', '=', True)])
        last_update = min(self.mapped(lambda r: r.last_update or datetime(1969, 1, 1, 1, 1, 1, 1)))
        for project in self:
            user_ids = project.allowed_user_ids.ids
            if len(user_ids) == 0 and project.wt_migration_id:
                user_ids = project.wt_migration_id.admin_user_ids.ids
            access_token = self.env['hr.employee'].search(
                [('user_id', 'in', user_ids),
                 ('wt_private_key', '!=', False)], order='is_wt_admin desc').mapped(
                'wt_private_key')
            if any(access_token) and project.wt_migration_id:
                project.wt_migration_id.update_project(project, access_token[0])
        if not last_update:
            last_update = datetime(1969, 1, 1, 1, 1, 1, 1)
        time.sleep(3)
        self._cr.commit()
        for wt in project.mapped('wt_migration_id'):
            wt.with_delay(eta=29).delete_work_logs_by_unix(int(last_update.timestamp() * 1000))
            wt.with_delay(eta=30).load_work_logs_by_unix(int(last_update.timestamp() * 1000))

    def reset_state(self):
        for record in self:
            record.last_update = False
