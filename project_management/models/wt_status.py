from odoo import api, fields, models, _


class JiraProject(models.Model):
    _name = "wt.status"
    _description = "Task Status"
    _order = 'sequence asc'

    sequence = fields.Integer(string='Sequence')
    name = fields.Char(string='Name')
    key = fields.Char(string='Key')
    # implied_project_ids = fields.Many2many('wt.project', string='Implied Projects')
