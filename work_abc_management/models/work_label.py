from datetime import datetime
from odoo import api, fields, models, _


class WorkLabel(models.Model):
    _name = "work.label"
    _description = "Label"

    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)