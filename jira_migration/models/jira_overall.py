import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class JiraStatus(models.Model):
    _inherit = "jira.status"

    jira_key = fields.Char(string='Jira Key')


class JiraTimeLog(models.Model):
    _inherit = "jira.time.log"

    id_on_jira = fields.Integer(string='ID on JIRA')

    def batch_export(self, pivot_time):
        ticket_ids = self.mapped('ticket_id')
        ticket_ids.write({'last_export': pivot_time})
        ticket_ids.export_time_log_to_jira()

    def render_batch_update_wizard(self):
        action = self.env.ref("jira_migration.export_work_log_action_form").read()[0]
        action["context"] = {'default_time_log_ids': self.ids}
        return action

    def write(self, values):
        res = super().write(values)
        self.ticket_id.jira_migration_id.update_time_logs(self.ticket_id, self)
        return res

    def unlink(self):
        try:
            if self.id_on_jira:
                self.ticket_id.jira_migration_id.delete_time_logs(self.ticket_id, self)
        except:
            pass
        return super().unlink()