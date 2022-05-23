from odoo import api, fields, models, _


class JiraProject(models.Model):
    _name = "jira.status"
    _description = "JIRA Status"
    _order = 'sequence asc'

    sequence = fields.Integer(string='Sequence')
    name = fields.Char(string='Name')
    key = fields.Char(string='Key')
    # implied_project_ids = fields.Many2many('jira.project', string='Implied Projects')
