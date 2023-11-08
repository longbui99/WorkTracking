from datetime import datetime
from odoo import api, fields, models, _


class WorkPriority(models.Model):
    _inherit = "work.priority"

    id_onhost = fields.Char(string="Server ID")
    host_id = fields.Many2one("work.base.integration", string="Host", ondelete="cascade")