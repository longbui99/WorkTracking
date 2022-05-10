from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    jira_username = fields.Char(string='JIRA Username')
    jira_password = fields.Char(string='JIRA Password')
    jira_migration_board = fields.Char(string='JIRA Migration Board')
    jira_private_key = fields.Many2one('jira.migration', string='JIRA Private Key')

