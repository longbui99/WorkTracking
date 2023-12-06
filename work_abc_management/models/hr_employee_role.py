from odoo import models, fields, api, _


class WorkAllocation(models.Model):
    _name = "hr.employee.role"
    _description = "Employee Role"
    _order = "id desc"

    name = fields.Char(string="Name", required=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", related="user_id.employee_id", store=True)
    user_id = fields.Many2one(comodel_name="res.users", string="User", required=True)
