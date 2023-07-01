from datetime import datetime
from odoo import api, fields, models, _


class WtLabel(models.Model):
    _name = "wt.label"
    _description = "Label"

    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)