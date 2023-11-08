import pytz
from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'export.work.log.pivot'
    _description = 'Task Load By Link'

    time_log_ids = fields.One2many('work.time.log', store=False)
    task_ids = fields.One2many('work.task', store=False)
    from_datetime = fields.Datetime(string="From Timestamp")

    def export(self):
        self.ensure_one()
        self.time_log_ids.batch_export(self.from_datetime)
        self.task_ids.batch_export(self.from_datetime)
