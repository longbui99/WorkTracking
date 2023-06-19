from odoo import api, fields, models, _


class AccessCode(models.Model):
    _name = "user.access.code"
    _description = "User Access Code"

    key = fields.Char(string='Key', index=True)
    uid = fields.Char(string='Value')
