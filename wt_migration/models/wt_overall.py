import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class JiraStatus(models.Model):
    _inherit = "wt.status"

    wt_key = fields.Char(string='Tasks Key')


class JiraTimeLog(models.Model):
    _inherit = "wt.time.log"

    id_on_wt = fields.Integer(string='ID on JIRA')

    def batch_export(self, pivot_time):
        ticket_ids = self.mapped('ticket_id')
        ticket_ids.write({'last_export': pivot_time})
        ticket_ids.export_time_log_to_wt()

    def render_batch_update_wizard(self):
        action = self.env.ref("wt_migration.export_work_log_action_form").read()[0]
        action["context"] = {'default_time_log_ids': self.ids}
        return action

    def write(self, values):
        res = super().write(values)
        self.ticket_id.wt_migration_id.update_time_logs(self.ticket_id, self)
        return res

    def unlink(self):
        try:
            if self.id_on_wt:
                self.ticket_id.wt_migration_id.delete_time_logs(self.ticket_id, self)
        except:
            pass
        return super().unlink()