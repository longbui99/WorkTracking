from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HREmployee(models.AbstractModel):
    _inherit = 'hr.employee.base'
    _parent_name = "parent_id"
    _parent_store = True

    maximum_search_result = fields.Integer(string="# Search Result", default=11)
    maximum_relative_result = fields.Integer(string="# Relative Active", default=4)
    order_style = fields.Char(string="Order Result")
    favorite_task_ids = fields.Many2many("work.task", string="Favorite Tasks")
    week_start = fields.Selection([('1', 'Monday'),
                                   ('2', 'Tuesday'),
                                   ('3', 'Wednesday'),
                                   ('4', 'Thursday'),
                                   ('5', 'Friday'),
                                   ('6', 'Saturday'),
                                   ('7', 'Sunday')], string='First Day of Week', required=True, default='1')
    rouding_up = fields.Integer(string="Rounding Up (minutes)", default=0)
    default_unit = fields.Selection([('m', 'Minute'),
                                     ('h', 'Hour'),
                                     ('d', 'Day'),
                                     ('w', 'Week')], string="Default Log Unit", required=True, default="m")
    todo_transition = fields.Boolean(string="Move Personal TODO to next date?", default=True)
    move_threshold = fields.Integer(string="Maximum TODO alive", default=7)
    default_nbr_days = fields.Integer(string="Default Show Tracking Last (days)", default=7)
    auto_remove_access = fields.Boolean(string="Auto Remove Access", default=True)
    maximum_connection = fields.Integer(string="Maximum Extension Connection", default=4)
    parent_path = fields.Char(index=True, unaccent=False)

    @api.constrains('default_nbr_days')
    def _check_default_nbr_days(self):
        for record in self:
            if record.default_nbr_days > 14 or record.default_nbr_days <= 0:
                raise UserError("Default Show Tracking must be less than 14 and greater than 0")

    def action_reset_extension_token(self):
        self.ensure_one()
        if self.user_id:
            self.env['user.access.code'].sudo().search([('uid', '=', self.env.user.id)]).unlink()