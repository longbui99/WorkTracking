from odoo import api, fields, models, _


class JiraProject(models.Model):
    _name = "jira.status"
    _description = "JIRA Status"
    _order = 'create_date desc'

    name = fields.Char(string='Name')
    implied_project_ids = fields.Many2many('jira.project', string='Implied Projects')
