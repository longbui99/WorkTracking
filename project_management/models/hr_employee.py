from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    maximum_search_result = fields.Integer(string="# Search Result", default=11)
    maximum_relative_result = fields.Integer(string="# Relative Active", default=4)
    order_style = fields.Char(string="Order Result")
