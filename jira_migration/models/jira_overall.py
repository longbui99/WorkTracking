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
