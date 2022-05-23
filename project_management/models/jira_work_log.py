from odoo import api, fields, models, _


class JiraWorkLog(models.Model):
    _name = "jira.work.log"
    _description = "JIRA Work Log"
    _order = 'create_date desc'

    start = fields.Datetime(string='Start')
    end = fields.Datetime(string='End')
    duration = fields.Integer(string='Duration (s)', compute='_compute_duration', store=True)
    description = fields.Text(string='Description', required=True)
    ticket_id = fields.Many2one('jira.ticket', string='Ticket')
    cluster_id = fields.Many2one('jira.work.log.cluster', string='Cluster')
    state = fields.Selection([('progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Canceled')], string='Status',
                             default='progress')
    source = fields.Char(string='Source')
    user_id = fields.Many2one('res.users', string='User', required=True)

    @api.depends('start', 'end')
    def _compute_duration(self):
        for record in self:
            if record.start and record.end:
                record.duration = (record.end - record.start).total_seconds()


class JiraWorkLogCluster(models.Model):
    _name = "jira.work.log.cluster"
    _description = "JIRA Work Log Cluster"

    name = fields.Char(string='Cluster Name')
