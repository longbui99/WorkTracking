from odoo import models, fields, api, _


class WtAllocation(models.Model):
    _name = "hr.employee.role"
    _description = "Employee Role"
    _order = "id desc"

    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", required=True)
    user_id = fields.Many2one(comodel_name="res.users", string="User", related="employee_id.user_id", store=True)
    name = fields.Char(string="Name", required=True)
