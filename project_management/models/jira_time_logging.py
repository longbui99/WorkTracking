from odoo import api, fields, models, _


class JiraTimeLog(models.Model):
    _name = "jira.time.log"
    _description = "JIRA Time Log"
    _order = 'create_date desc'

    name = fields.Char(string='Name', required=True)
    time = fields.Char(string='Time Logging', required=True)
    description = fields.Html(string='Description', required=True)
    ticket_id = fields.Many2one('jira.ticket', string='Ticket', required=True)
    minutes = fields.Integer(string='Minutes', required=True)
