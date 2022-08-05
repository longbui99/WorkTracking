from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'wt.done.work.log'
    _description = 'JIRA Done Work Log'

    log_text = fields.Char(string="Work Logs", required=True)
    log_date = fields.Datetime(string="Start Date", default=fields.Datetime.now)
    log_description = fields.Char(string="Description", required=True)
    ticket_id = fields.Many2one("wt.ticket", string="Ticket", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.ticket_id.action_manual_work_log({
            'description': self.log_description,
            'time': self.log_text,
            'log_date': self.log_date
        })
