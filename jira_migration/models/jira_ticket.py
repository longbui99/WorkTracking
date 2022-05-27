import datetime
from odoo import api, fields, models, _


class JiraProject(models.Model):
    _inherit = "jira.ticket"

    jira_migration_id = fields.Many2one('jira.migration', string='Jira Migration')
    status_value = fields.Char(related='status_id.jira_key', store=True)
    last_export = fields.Datetime("Last Export Time")

    def export_time_log_to_jira(self):
        for record in self:
            record.jira_migration_id.export_time_log(record)
        self.last_export = datetime.datetime.now()

    def import_ticket_jira(self):
        for record in self:
            record.jira_migration_id._search_load('ticket', [record.ticket_key])

    def action_done_work_log(self, values={}):
        res = super().action_done_work_log(values)
        if any(res.env['hr.employee'].search([('user_id', '=', self.env.user.id)]).mapped('auto_export_work_log')):
            res.filtered(lambda r: r.jira_migration_id.auto_export_work_log).export_time_log_to_jira()
        return res

    def action_manual_work_log(self, values={}):
        self.ensure_one()
        res = super().action_manual_work_log(values)
        if any(res.env['hr.employee'].search([('user_id', '=', res.env.user.id)]).mapped('auto_export_work_log')):
            if res.jira_migration_id.auto_export_work_log:
                res.jira_migration_id.export_time_log(res)
        return res

    @api.model
    def create(self, values):
        res = super().create(values)
        res.last_export = datetime.datetime.now()
        return res
