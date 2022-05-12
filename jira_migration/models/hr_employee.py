from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    jira_private_key = fields.Char(string='Access Token')
    # jira_migration_board = fields.Many2one('jira.migration', string='JIRA Migration Board')

