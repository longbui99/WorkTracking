from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.project_management.utils.time_parsing import convert_second_to_time_format, \
    convert_second_to_log_format

PARSER = {
    'kickoff': "Kick-Off Meeting",
    "demo": "Demo Meeting"
}


class KickOffSession(models.TransientModel):
    _name = 'jira.chain.work.session'
    _description = 'JIRA Kick Of Session'
    _order = "create_date desc"

    name = fields.Char(string="Name")
    project_id = fields.Many2one('jira.project', string="Project")
    ticket_id = fields.Many2one('jira.ticket', string="Ticket")
    start = fields.Datetime(string="Start At")
    ticket_chain_work_ids = fields.One2many('jira.chain.work.session.line', 'chain_work_id', string="Tickets")
    state = fields.Selection([('draft', 'Draft'),
                              ('progress', 'In Progress'),
                              ('done', 'Done'),
                              ('logged', "Logged")],
                             compute='_compute_state', store=True
                             )
    description = fields.Char(string="Description")
    logging_type = fields.Selection([('ticket', 'To the specific ticket'),
                                     ('separate', 'In separated')], default='separate')
    log_to_ticket_id = fields.Many2one('jira.ticket', string="Ticket")

    @api.depends('ticket_chain_work_ids', 'ticket_chain_work_ids.state')
    def _compute_state(self):
        for record in self:
            status = record.ticket_chain_work_ids.mapped('state')
            if 'progress' in status:
                record.state = 'progress'
            elif status and 'draft' not in status:
                record.state = 'done'
            else:
                record.state = 'draft'

    def get_free_ticket(self):
        self.ensure_one()
        tickets = self.ticket_chain_work_ids.filtered(lambda r: r.state == 'draft')
        if tickets:
            return tickets[0]
        else:
            return False

    def update_processing(self):
        next_line = self.ticket_chain_work_ids.filtered(lambda r: r.state == 'draft')
        current_line = self.ticket_chain_work_ids.filtered(lambda r: r.state == 'progress')
        if current_line:
            current_line.action_done()
        if next_line:
            next_line[0].action_progress()
            return next_line[0].ticket_id

    def reload_chain(self):
        self.ensure_one()
        if self._context.get("mobile"):
            action = self.env["ir.actions.actions"]._for_xml_id("project_management.log_work_action_mobile_form_view")
        else:
            action = self.env["ir.actions.actions"]._for_xml_id("project_management.log_work_action_form_view")
        action["res_id"] = self.id
        return action

    def action_next(self):
        self.ensure_one()
        if not self.ticket_chain_work_ids:
            raise UserError('Need at least one ticket')
        self.ticket_id = self.update_processing()
        self.start = datetime.now()
        return self.reload_chain()

    def action_done(self):
        self.ensure_one()
        self.ticket_chain_work_ids.filtered(lambda r: r.state == 'draft').unlink()
        progresses = self.ticket_chain_work_ids.filtered(lambda r: r.state == 'progress')
        if progresses:
            progresses.action_done()
            return self.reload_chain()
        if self.logging_type == "ticket":
            time = convert_second_to_log_format(sum(self.ticket_chain_work_ids.mapped('duration')))
            description = "\n".join(
                self.ticket_chain_work_ids.mapped(lambda
                                                      r: f"[{convert_second_to_log_format(r.duration)}][{r.ticket_id.ticket_key}]: {r.description}"))
            self.log_to_ticket_id.action_manual_work_log({
                "source": "Internal Chain",
                "description": description,
                "time": time
            })
        elif self.logging_type == "separate":
            for ticket in self.ticket_chain_work_ids:
                ticket.ticket_id.action_manual_work_log({
                    "source": "Internal Chain",
                    "description": ticket.description or '',
                    "time": convert_second_to_log_format(ticket.duration)
                })
        self.state = "logged"
        return {'type': 'ir.actions.act_window_close'}

    @api.model
    def default_get(self, fields):
        result = super(KickOffSession, self).default_get(fields)
        return result

    @api.model
    def create(self, values):
        if 'description' not in values:
            values['description'] = values.get('name')
        return super().create(values)


class KickOffSessionLine(models.TransientModel):
    _name = 'jira.chain.work.session.line'
    _description = 'JIRA Kick Of Session Line'
    _order = 'sequence asc, create_date asc'

    sequence = fields.Integer(string="Sequence")
    chain_work_id = fields.Many2one('jira.chain.work.session', string="Kick Off")
    ticket_id = fields.Many2one("jira.ticket", string="Ticket")
    state = fields.Selection([('draft', 'Draft'),
                              ('progress', 'In Progress'),
                              ('done', 'Done')], default="draft")
    duration = fields.Integer(string="Duration", compute='_compute_duration', store=True)
    description = fields.Char(string="Description")
    time = fields.Char(string="Duration in Text", compute="_compute_time", store=True)
    start = fields.Datetime(string="Start")
    end = fields.Datetime(string="End")

    @api.depends('start', 'end')
    def _compute_duration(self):
        for record in self:
            if record.start and record.end:
                record.duration = (record.end - record.start).total_seconds()

    @api.depends('duration')
    def _compute_time(self):
        for record in self:
            record.time = convert_second_to_time_format(record.duration)

    def action_done(self):
        for record in self:
            record.state = 'done'
            record.start = record.chain_work_id.start
            record.end = datetime.now()
            record.description = record.chain_work_id.description

    def action_progress(self):
        for record in self:
            record.state = 'progress'


class KickOffBase(models.TransientModel):
    _name = 'jira.chain.work.base'
    _description = 'JIRA Kick Of base'

    name = fields.Char(string="Name")
    type = fields.Selection([('manual', 'Select manually')], default='manual')
    template = fields.Selection([('kickoff', 'Kick-off'),
                                 ('demo', 'Demo')])
    project_id = fields.Many2one('jira.project', string="Project")

    #
    # def prepare_kickoff_line_data(self):
    #     pass

    def loading_ticket(self):
        self.ensure_one()
        res = {
            'project_id': self.project_id.id,
            'description': PARSER.get(self.template, ''),
            "name": self.name
        }
        # if self.type == "current_sprint":
        #     jql = f"jql=project={self.project_id.project_key} AND Sprint in openSprints() AND assignee = {}"
        # elif self.type == "next_sprint":
        #     pass
        return self.env['jira.chain.work.session'].create(res)

    def action_start(self):
        self.ensure_one()
        if self.project_id:
            action = self.env["ir.actions.actions"]._for_xml_id("project_management.log_work_action_form_view")
            action['res_id'] = self.loading_ticket().id
            return action
