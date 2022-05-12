from odoo import api, fields, models, _


class JiraTimeLog(models.Model):
    _name = "jira.time.log"
    _description = "JIRA Time Log"
    _order = 'create_date desc'

    name = fields.Char(string='Name', required=True)
    time = fields.Char(string='Time Logging')
    description = fields.Html(string='Description', required=True)
    ticket_id = fields.Many2one('jira.ticket', string='Ticket')
    duration = fields.Integer(string='Duration', required=True)
    cluster_id = fields.Many2one('jira.work.log.cluster')
    state = fields.Selection([('progress', 'In Progress'), ('done', 'Done')], string='Status', default='progress')
    source = fields.Char(string='Source')
    user_id = fields.Many2one('res.users', string='User')
