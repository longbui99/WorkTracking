from odoo import api, fields, models, _


class OneTimeLink(models.Model):
    _name = "one.time.link"
    _description = "One Time Link"

    key = fields.Char(string='Key', index=True)
    value = fields.Char(string='Value')
