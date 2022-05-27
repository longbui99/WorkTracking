from datetime import datetime
from odoo import api, fields, models, _
from odoo.addons.project_management.utils.time_parsing import convert_second_to_log_format, convert_log_format_to_second


class JiraTimeLog(models.Model):
    _name = "jira.time.log"
    _description = "JIRA Time Log"
    _order = 'start_date desc'
    _rec_name = 'ticket_id'

    time = fields.Char(string='Time Logging', compute='_compute_time_data', store=True)
    description = fields.Text(string='Description', required=True)
    ticket_id = fields.Many2one('jira.ticket', string='Ticket')
    duration = fields.Integer(string='Duration', required=True)
    cluster_id = fields.Many2one('jira.work.log.cluster')
    state = fields.Selection([('progress', 'In Progress'), ('done', 'Done')], string='Status', default='progress')
    source = fields.Char(string='Source')
    user_id = fields.Many2one('res.users', string='User')
    start_date = fields.Datetime("Start Date")

    @api.depends('duration')
    def _compute_time_data(self):
        for record in self:
            if record.duration:
                record.time = convert_second_to_log_format(record.duration)

    def unlink(self):
        cluster_ids = self.mapped('cluster_id')
        self.mapped('ticket_id').mapped('work_log_ids').filtered(lambda r: r.cluster_id in cluster_ids).write(
            {'state': 'cancel'})
        return super().unlink()

    @api.model
    def create(self, values):
        if 'time' in values:
            values['duration'] = convert_log_format_to_second(values['time'])
            values.pop('time')
        if 'start_date' not in values:
            values['start_date'] = datetime.now()
        return super().create(values)
