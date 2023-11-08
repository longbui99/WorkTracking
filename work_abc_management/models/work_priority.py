from datetime import datetime
from odoo import api, fields, models, _


class WorkPriority(models.Model):
    _name = "work.priority"
    _description = "Task Priority"
    _order = 'sequence, id desc'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string="Name", required=True)
    icon_url = fields.Char(string="URL")
    company_id = fields.Many2one("res.company", string="Company")