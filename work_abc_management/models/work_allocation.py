from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo.addons.work_abc_management.utils.time_parsing import get_date_range


class WorkAllocation(models.Model):
    _name = "work.allocation"
    _description = "WT Allocation"
    _order = "start_date desc, id desc"

    user_id = fields.Many2one(comodel_name="res.users", string="User", required=True)
    allocation_group_id = fields.Many2one(comodel_name="work.allocation.group", string="Allocation Group")
    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", store=True)
    finance_id = fields.Many2one(comodel_name="work.finance", string="Finance Plan")
    project_id = fields.Many2one(comodel_name="work.project", string="Project", required=True)
    allocation = fields.Float(string="Allocation (hrs)", required=True)
    employee_role_id = fields.Many2one(comodel_name="hr.employee.role", string="Role")
    cost_per_hour = fields.Monetary(string="Cost", group="work_abc_management.group_work_finance_manager")
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    is_compute_timeline = fields.Boolean(string="Impact Timeline?")
    start_date = fields.Datetime(string="Start Date", default=lambda self: fields.Datetime.now())
    end_date = fields.Datetime(string="End Date", default=lambda self: fields.Datetime.now())
    standard_deviation = fields.Float(string="Standard Deviation", default=0.2)
    filter_date = fields.Char(string="Filter", store=False, search='_search_filter_date')
    generated_from_group = fields.Boolean(string="Generated From Group", )

    def _search_filter_date(self, operator, operand):
        if operator == "=":
            start_date, end_date = get_date_range(self, operand)
            domain = [
                '|',
                '|',
                '&',
                ('start_date', '>=', start_date),
                ('end_date', '<=', end_date),
                '&',
                ('end_date', '>=', end_date),
                ('start_date', '<=', end_date),
                '&',
                ('start_date', '<=', start_date),
                ('end_date', '>=', start_date)
            ]
            ids = self.search(domain)
            return [('id', 'in', ids.ids)]
        raise UserError(_("Search operation not supported"))
    
    def unlink(self):
        if not self._context.get('delete_from_group') and self.mapped('allocation_group_id'):
            raise UserError("Cannot delete the allocation since it's link to the allocation group")
        return super().unlink()


class WorkAllocationGroup(models.Model):
    _name = "work.allocation.group"
    _description = "WT Allocation Group"
    _order = "start_date desc, end_date desc"

    name = fields.Char(string="Name", compute="_compute_name")
    user_id = fields.Many2one(comodel_name="res.users", string="User", required=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", string="Employee", related="user_id.employee_id", store=True)
    finance_id = fields.Many2one(comodel_name="work.finance", string="Finance Plan")
    project_id = fields.Many2one(comodel_name="work.project", string="Project", required=True)
    employee_role_id = fields.Many2one(comodel_name="hr.employee.role", string="Role")
    allocation = fields.Float(string="Allocation (hrs)", required=True)
    cost_per_hour = fields.Monetary(string="Cost", group="work_abc_management.group_work_finance_manager")
    standard_deviation = fields.Float(string="Standard Deviation", default=0.2)
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
    ], string="Allocation Type", default="week", required=True, readonly=True)
    allocation_ids = fields.One2many("work.allocation", "allocation_group_id", string="Allocations")
    today_allocation = fields.Float(string="Current Allocation", compute="_compute_today_allocation")

    @api.depends('allocation_ids')
    def _compute_today_allocation(self):
        today = fields.Datetime.now()
        current_allocations = self.allocation_ids.filtered(lambda allocation: allocation.start_date < today and allocation.end_date > today)
        allocation_by_group = {allocation.allocation_group_id: allocation for allocation in current_allocations}
        for allocation_group in self:
            allocation_group.today_allocation = allocation_by_group.get(allocation_group).allocation if allocation_by_group.allocation_ids else 0

    @api.depends("user_id", "project_id", "finance_id", "employee_role_id", "start_date", "end_date")
    def _compute_name(self):
        for group in self:
            if isinstance(group.id, int):
                start_date = group.start_date.strftime("%b %d, %Y")
                end_date = group.end_date.strftime("%b %d, %Y")
                group.name = f"[{group.project_id.project_key}] {group.employee_role_id.name + ' - ' if group.employee_role_id else '' }{group.user_id.name} ({start_date} - {end_date})"
            else:
                group.name = "Creating..."

    @api.onchange('finance_id')
    def _onchange_finance(self):
        if not self.project_id or (self.finance_id and self.project_id != self.finance_id.project_id):
            self.project_id = self.finance_id.project_id
        if self.finance_id.start_recurrence_date:
            self.start_date = self.finance_id.start_recurrence_date
        if self.finance_id.due_date:
            self.end_date = self.finance_id.due_date
        
    @api.onchange('project_id')
    def _onchange_project(self):
        if self.finance_id and self.finance_id.project_id != self.project_id:
            self.finance_id = False

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
            'standard_deviation': self.standard_deviation,
            'generated_from_group': True
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
    
    def action_open_allocations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('work_abc_management.action_work_allocation')
        action['context'] = {}
        action['domain'] = [('id', 'in', self.allocation_ids.ids)]
        return action

    def action_clear_allocations(self):
        self.mapped('allocation_ids').with_context(delete_from_group=True).unlink()
    
    def write(self, values):
        res = super().write(values)
        if 'finance_id' in values:
            self.mapped('allocation_ids').write({'finance_id': values['finance_id']})
        return res

    @api.constrains('start_date', 'end_date')
    def _check_change_period_doable(self):
        for group in self:
            if group.allocation_ids:
                raise UserError("You cannot change neither Start Date nor End Date since it's generated allocation")