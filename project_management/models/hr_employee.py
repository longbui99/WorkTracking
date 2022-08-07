from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    maximum_search_result = fields.Integer(string="# Search Result", default=11)
    maximum_relative_result = fields.Integer(string="# Relative Active", default=4)
    order_style = fields.Char(string="Order Result")
    favorite_ticket_ids = fields.Many2many("jira.ticket", string="Favorite Issues")
    week_start = fields.Selection([('1', 'Monday'),
                                   ('2', 'Tuesday'),
                                   ('3', 'Wednesday'),
                                   ('4', 'Thursday'),
                                   ('5', 'Friday'),
                                   ('6', 'Saturday'),
                                   ('7', 'Sunday')], string='First Day of Week', required=True, default='1')
