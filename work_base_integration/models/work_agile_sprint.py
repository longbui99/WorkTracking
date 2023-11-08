from odoo import models, api, fields, _


class AgileSprint(models.Model):
    _inherit = "agile.sprint"
    _order = "id_onhost desc, name desc, state_sequence asc, id desc"

    id_onhost = fields.Integer(string="ID on Task")
    updated = fields.Boolean(string="Updated?")