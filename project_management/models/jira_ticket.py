from odoo import api, fields, models, _


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
    progress_start_time = fields.Datetime(string='Progress Start Time')
    story_point = fields.Integer(string='Story Point')
    project_id = fields.Many2one('jira.project', string='Project', required=True)
    assignee_id = fields.Many2one('res.users', string='Assignee')
    suitable_assignee = fields.Many2many('res.users', store=False, compute='_compute_suitable_assignee', compute_sudo=True)

    def __assign_assignee(self):
        for record in self:
            if record.project_id:
                record.suitable_assignee = record.project_id.allowed_user_ids.ids

    def _compute_suitable_assignee(self):
        self.__assign_assignee()

    @api.onchange('project_id')
    def _onchange_project_id(self):
        self.__assign_assignee()
