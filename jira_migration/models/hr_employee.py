from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    jira_private_key = fields.Char(string='Access Token', tracking=True)
    # jira_migration_board = fields.Many2one('jira.migration', string='JIRA Migration Board')
    auto_export_work_log = fields.Boolean(string='Auto Export Logs', tracking=True)
