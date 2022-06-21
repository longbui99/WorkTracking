import pytz
from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'export.work.log.pivot'
    _description = 'JIRA Load By Link'

    time_log_ids = fields.One2many('jira.time.log', store=False)
    ticket_ids = fields.One2many('jira.ticket', store=False)
    from_datetime = fields.Datetime(string="From Timestamp")

    def export(self):
        self.ensure_one()
        pivot_time = self.from_datetimereplace(tzinfo=pytz.utc).astimezone(
            pytz.timezone(self.env.user.tz or 'UTC')).replace(tzinfo=None)
        self.time_log_ids.batch_export(pivot_time)
        self.ticket_ids.batch_export(pivot_time)
