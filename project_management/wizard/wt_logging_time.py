from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'wt.done.work.log'
    _description = 'Task Done Work Log'

    log_text = fields.Char(string="Work Logs", required=True)
    log_date = fields.Datetime(string="Start Date", default=fields.Datetime.now)
    log_description = fields.Char(string="Description", required=True)
    issue_id = fields.Many2one("wt.issue", string="Ticket", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.issue_id.action_manual_work_log({
            'description': self.log_description,
            'time': self.log_text,
            'log_date': self.log_date
        })
