from odoo import models, api, fields, _


class AgileSprint(models.Model):
    _inherit = "agile.sprint"

    id_on_wt = fields.Integer(string="ID on Task")
    updated = fields.Boolean(string="Updated?")