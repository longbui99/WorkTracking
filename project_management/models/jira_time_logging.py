from odoo import api, fields, models, _


class JiraTimeLog(models.Model):
    _name = "jira.time.log"
    _description = "JIRA Time Log"
    _order = 'create_date desc'
    _rec_name = 'ticket_id'

    time = fields.Char(string='Time Logging', compute='_compute_time_data', store=True)
    description = fields.Text(string='Description', required=True)
    ticket_id = fields.Many2one('jira.ticket', string='Ticket')
    duration = fields.Integer(string='Duration', required=True)
    cluster_id = fields.Many2one('jira.work.log.cluster')
    state = fields.Selection([('progress', 'In Progress'), ('done', 'Done')], string='Status', default='progress')
    source = fields.Char(string='Source')
    user_id = fields.Many2one('res.users', string='User')

    @api.model
    def convert_second_to_log_format(self, time):
        data = [{'key': 'w', 'duration': 604800},
                {'key': 'd', 'duration': 86400},
                {'key': 'h', 'duration': 3600},
                {'key': 'm', 'duration': 60},
                {'key': 's', 'duration': 1}]
        response = ""
        for segment in data:
            duration = segment['duration']
            if time >= duration:
                response += f"{int(time / duration)}{segment['key']} "
                time -= (int(time / duration) * duration)
        return response

    @api.depends('duration')
    def _compute_time_data(self):
        for record in self:
            if record.duration:
                record.time = self.convert_second_to_log_format(record.duration)

    def unlink(self):
        cluster_ids = self.mapped('cluster_id')
        self.mapped('ticket_id').mapped('work_log_ids').filtered(lambda r: r.cluster_id in cluster_ids).write({'state': 'cancel'})
        return super().unlink()