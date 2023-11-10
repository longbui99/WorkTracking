from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WorkAllocation(models.Model):
    _name = "work.allocation"
    _description = "WT Allocation"
    _order = "start_date desc, id desc"

    user_id = fields.Many2one(comodel_name="res.users", string="User", required=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", related="user_id.employee_id", store=True)
    finance_id = fields.Many2one(comodel_name="work.finance", string="Finance Plan")
    project_id = fields.Many2one(comodel_name="work.project", string="Project", required=True)
    allocation = fields.Float(string="Allocation (hrs)", required=True)
    employee_role_id = fields.Many2one(comodel_name="hr.employee.role", string="Role")
    cost_per_hour = fields.Monetary(string="Cost")
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    is_compute_timeline = fields.Boolean(string="Impact Timeline?")
    start_date = fields.Datetime(string="Start Date", default=lambda self: fields.Datetime.now())
    end_date = fields.Datetime(string="End Date", default=lambda self: fields.Datetime.now())
    allocation_group_id = fields.Many2one(comodel_name="work.allocation.group", string="Allocation Group")

class WorkAllocationGroup(models.Model):
    _name = "work.allocation.group"
    _description = "WT Allocation Group"
    _order = "start_date desc, end_date desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    user_id = fields.Many2one(comodel_name="res.users", string="User", required=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", related="user_id.employee_id", store=True)
    finance_id = fields.Many2one(comodel_name="work.finance", string="Finance Plan")
    project_id = fields.Many2one(comodel_name="work.project", string="Project", required=True)
    employee_role_id = fields.Many2one(comodel_name="hr.employee.role", string="Role")
    allocation = fields.Float(string="Allocation (hrs)", required=True)
    cost_per_hour = fields.Monetary(string="Cost")
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    is_compute_timeline = fields.Boolean(string="Impact Timeline?")
    start_date = fields.Datetime(string="Start Date", default=lambda self: fields.Datetime.now())
    end_date = fields.Datetime(string="End Date", default=lambda self: fields.Datetime.now())
    allocation_type = fields.Selection([
        ("date", "Daily"),
        ("week", "Weekly"),
        ("bi-week", "Bi-Weekly"),
        ("month", "Monthly"),
        ("quater", "Quaterly"),
        ("anual", "Anually")
    ], string="Allocation Type", default="week", required=True)

    allocation_ids = fields.One2many("work.allocation", "allocation_group_id", string="Allocations")

    @api.depends("user_id", "project_id", "finance_id", "employee_role_id", "start_date", "end_date")
    def _compute_name(self):
        for group in self:
            if isinstance(group.id, int):
                start_date = group.start_date.strftime("%b %d, %Y")
                end_date = group.end_date.strftime("%b %d, %Y")
                group.name = f"[{group.project_id.project_key}] {group.employee_role_id.name} - {group.user_id.name} ({start_date} - {end_date})"
            else:
                group.name = "Creating..."

    def action_clear_allocations(self):
        self.mapped('allocation_ids').unlink()

    def _generate_allocations(self, values, start_date, end_date, increasement):
        value_list = []
        while start_date < end_date:
            step_values = values.copy()
            step_values.update({
                'start_date': start_date,
                'end_date': start_date + increasement,
                'allocation_group_id': self.id,
            })
            value_list.append(step_values)
            start_date += increasement
        return value_list

    def _prepare_allocation_values(self):
        self.ensure_one()
        return {
            'user_id': self.user_id.id,
            'finance_id': self.finance_id.id,
            'project_id': self.project_id.id,
            'employee_role_id': self.employee_role_id.id,
            'cost_per_hour': self.cost_per_hour,
            'currency_id': self.currency_id.id,
            'allocation': self.allocation,
            'is_compute_timeline': self.is_compute_timeline,
        }
    
    def __get_margin_number(self):
        self.ensure_one()
        margin = False
        if self.allocation_type == "date":
            margin = relativedelta(days=1)
        elif self.allocation_type == "week":
            margin = relativedelta(days=7)
        elif self.allocation_type == "bi-week":
            margin = relativedelta(days=14)
        elif self.allocation_type == "month":
            margin = relativedelta(monthss=1)
        elif self.allocation_type == "quater":
            margin = relativedelta(months=3)
        elif self.allocation_type == "anual":
            margin = relativedelta(years=1)
        return margin

    def _action_generate_allocations(self):
        self.ensure_one()
        values = self._prepare_allocation_values()
        margin = self.__get_margin_number()
        if not margin:
            raise UserError("The Allocation Type is incorrect %s" % self.allocation_type)
        allocation_values = self._generate_allocations(values, self.start_date, self.end_date, margin)
        return self.env['work.allocation'].create(allocation_values)

    def action_generate_allocations(self):
        allocations = self.env['work.allocation']
        for group in self:
            allocations |= group._action_generate_allocations()
        return allocations