import pytz
from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'export.work.log.pivot'
    _description = 'Tasks Load By Link'

    time_log_ids = fields.One2many('wt.time.log', store=False)
    ticket_ids = fields.One2many('wt.ticket', store=False)
    from_datetime = fields.Datetime(string="From Timestamp")

    def export(self):
        self.ensure_one()
        self.time_log_ids.batch_export(self.from_datetime)
        self.ticket_ids.batch_export(self.from_datetime)
