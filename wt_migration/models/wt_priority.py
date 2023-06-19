from datetime import datetime
from odoo import api, fields, models, _


class WtPriority(models.Model):
    _inherit = "wt.priority"

    id_on_wt = fields.Char(string="Server ID")
    wt_migration_id = fields.Many2one("wt.migration", string="Migration", ondelete="cascade")