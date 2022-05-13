import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class JiraProject(models.Model):
    _name = "jira.ticket"
    _description = "JIRA Ticket"
    _order = 'pin desc, sequence asc, create_date desc'
    _rec_name = 'ticket_key'

    pin = fields.Boolean(string='Pin')
    sequence = fields.Integer(string='Sequence')
    ticket_name = fields.Char(string='Name', required=True)
    ticket_key = fields.Char(string='Ticket Key')
    ticket_url = fields.Char(string='JIRA Ticket')
    time_log_ids = fields.One2many('jira.time.log', 'ticket_id', string='Log Times')
    story_point = fields.Integer(string='Story Point')
    project_id = fields.Many2one('jira.project', string='Project', required=True)
    assignee_id = fields.Many2one('res.users', string='Assignee')
    suitable_assignee = fields.Many2many('res.users', store=False, compute='_compute_suitable_assignee',
                                         compute_sudo=True)
    status_value = fields.Char('Status Raw Value', related='status_id.key')
    status_id = fields.Many2one('jira.status', string='Status')
    duration = fields.Integer('Duration', compute='_compute_duration', store=True)
    progress_cluster_id = fields.Many2one('jira.work.log.cluster', string='Progress Cluster')
    work_log_ids = fields.One2many('jira.work.log', 'ticket_id', string='Work Log Statuses')

    @api.depends('time_log_ids', 'time_log_ids.duration')
    def _compute_duration(self):
        for record in self:
            record.duration = sum(record.time_log_ids.mapped('duration'))

    def __assign_assignee(self):
        for record in self:
            if record.project_id:
                record.suitable_assignee = record.project_id.allowed_user_ids.ids

    def _compute_suitable_assignee(self):
        self.__assign_assignee()

    @api.onchange('project_id')
    def _onchange_project_id(self):
        self.__assign_assignee()

    def action_pause_work_log(self, values={}):
        source = values.get('source', 'internal')
        for record in self:
            domain = [
                ('cluster_id', '=', record.progress_cluster_id.id),
                ('state', '=', 'progress'),
                ('source', '=', source),
                ('user_id', '=', self.env.user.id)
            ]
            suitable_time_log = record.work_log_ids.filtered_domain(domain)
            suitable_time_log.write({
                'end': datetime.datetime.now(),
                'state': 'done'
            })

    def generate_progress_work_log(self, values={}):
        source = values.get('source', 'internal')
        self.action_pause_work_log()
        for record in self:
            if not record.progress_cluster_id:
                record.progress_cluster_id = self.env['jira.work.log.cluster'].create({
                    'name': self.ticket_key + "-" + str(len(record.time_log_ids) + 1)
                })
            if not record.time_log_ids.filtered(lambda r: r.cluster_id == record.progress_cluster_id):
                record.time_log_ids = [fields.Command.create({
                    'description': '',
                    'duration': 0.0,
                    'cluster_id': record.progress_cluster_id.id,
                    'user_id': self.env.user.id,
                    'source': source
                })]
            record.work_log_ids = [fields.Command.create({
                'start': datetime.datetime.now(),
                'cluster_id': record.progress_cluster_id.id,
                'user_id': self.env.user.id,
                'source': source
            })]
        return self

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
            if time > duration:
                response += f"{int(time/duration)}{segment['key']} "
                time -= (int(time/duration) * duration)
        return response

    def action_done_work_log(self, values={}):
        self.action_pause_work_log()
        source = values.get('source', 'internal')
        for record in self:
            domain = [
                ('cluster_id', '=', record.progress_cluster_id.id),
                ('source', '=', source),
                ('user_id', '=', self.env.user.id)
            ]
            work_log_ids = record.work_log_ids.filtered_domain(domain)
            if work_log_ids:
                work_log_ids.write({'state': 'done'})
            time_log_id = record.time_log_ids.filtered_domain(domain + [('state', '=', 'progress')])
            total_duration = sum(work_log_ids.mapped('duration'))
            if time_log_id:
                time_log_id.update({
                    'duration': total_duration,
                    'state': 'done',
                    'description': values.get('comment', ''),
                    'time': self.convert_second_to_log_format(total_duration)
                })
            record.progress_cluster_id = None
        return self
