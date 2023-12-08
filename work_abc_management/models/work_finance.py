import ast

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class WorkFinance(models.Model):
    _name = "work.finance"
    _description = "Finance Analytic"
    _order = 'sequence, id desc'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company.id, required=True)
    work_budget_ids = fields.One2many("work.budget", 'finance_id', string="Budgets")

    duration = fields.Float(string="Total Duration", compute='_compute_current_duration_used')
    duration_used = fields.Float(string="Total Used Duration", compute="_compute_current_duration_used")
    duration_percent_used = fields.Float(string="Duration Used Percent", compute="_compute_current_duration_used")

    amount = fields.Float(string="Total Amount", compute="_compute_current_duration_used")
    amount_used = fields.Float(string="Total Amount", compute="_compute_current_duration_used")
    amount_percent_used = fields.Float(string="Total Amount", compute="_compute_current_duration_used")

    budget_count = fields.Integer(string="Budget Count", compute="_compute_current_duration_used")
    project_id = fields.Many2one("work.project", string="Project", required=True)
    access_user_ids = fields.Many2many("res.users", "access_finance_user_rel", string="Accessible Users")
    start_recurrence_date = fields.Datetime(string="Start Recurrence Date")
    due_date = fields.Datetime(string="End Date", default=lambda self: fields.Datetime.now())
    recurrence_budget_id = fields.Many2one("work.budget", string="Recurrence Budget")
    recurrence_type = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('anually', 'Anually')
    ], string="Recurrence Type")

    def _compute_current_duration_used(self):
        self.mapped('work_budget_ids.duration_used')
        self.mapped('work_budget_ids.amount_used')
        for finance in self:
            finance.duration = sum(finance.work_budget_ids.mapped('duration'))
            finance.duration_used = sum(finance.work_budget_ids.mapped('duration_used'))
            finance.duration_percent_used = 100*finance.duration_used/finance.duration if finance.duration else 0
            finance.budget_count = len(finance.work_budget_ids)

            finance.amount = sum(finance.work_budget_ids.mapped('amount'))
            finance.amount_used = sum(finance.work_budget_ids.mapped('amount_used'))
            finance.amount_percent_used = 100*finance.amount_used/finance.amount if finance.amount else 0

    def get_period_from_to(self, from_date, to_date, interval_type='monthly'):
        kwargs = dict()
        if interval_type == "monthly":
            kwargs['months'] = 1
        elif interval_type == "weekly":
            kwargs['weeks'] = 1
        elif interval_type == "quarterly":
            kwargs['months'] = 3
        elif interval_type == "anually":
            kwargs['years'] = 1
        
        from_date += relativedelta(hour=0, minute=0, second=0)
        to_date += relativedelta(hour=0, minute=0, second=0)
        time_relativedelta = relativedelta(**kwargs)

        segment = []
        while from_date < to_date:
            segment.append({
                'start_date': from_date,
                'end_date': from_date + time_relativedelta
            })
            from_date += time_relativedelta
        return segment
    
    def _sanity_recurrence_generation(self):
        self.ensure_one()
        if not self.start_recurrence_date:
            raise UserError("You must indicate the Start Recurrence Date")
        if not self.due_date:
            raise UserError("You must indicate the End Date")
        if not self.recurrence_budget_id:
            raise UserError("You must indicate the Budget Template")
        
        if self.start_recurrence_date > self.due_date:
            raise UserError("End Date must be greater than Start Recurrence Date")


    def generate_recurrence_budget(self):
        self._sanity_recurrence_generation()

        budgets = self.work_budget_ids
        
        interval_periods = self.get_period_from_to(self.start_recurrence_date, self.due_date)
        
        budget_count = len(budgets)
        interval_count = len(interval_periods)

        to_update_budgets, to_remove_budgets = False, False
        to_generate_budgets, budget_periods = [], []

        if budget_count > interval_count:
            to_remove_budgets = budgets[interval_count:]
            to_update_budgets = budgets[:interval_count]
            budget_periods = interval_periods[interval_count:]
        elif budget_count < interval_count:
            to_generate_budgets = interval_periods[budget_count:]
            to_update_budgets = budgets
            budget_periods = interval_periods[:budget_count]

        if to_remove_budgets:
            to_remove_budgets.unlink()

        if budget_periods and to_update_budgets:
            for budget, interval in zip(to_update_budgets, budget_periods):
                for key, val in interval.items():
                    if budget[key] != val:
                        budget[key] = val
        
        if to_generate_budgets:
            for interval_period in to_generate_budgets:
                new_budget = self.recurrence_budget_id.copy()
                new_budget.update(interval_period)
                new_budget.freeze_duration = True
                new_budget.finance_id = self.id
        
        if not self.recurrence_budget_id:
            self.recurrence_budget_id = self.work_budget_ids[0].id

    def generate_recurrence_budgets(self):
        for finance in self:
            finance.generate_recurrence_budget()

    @api.model
    def create(self, value_list):
        records = super().create(value_list)
        recurrence_records = records.filtered(lambda record: record.recurrence_type)
        recurrence_records.generate_recurrence_budgets()
        return records
    
    def write(self, values):
        res = super().write(values)
        if (
            'start_recurrence_date' in values or
            'due_date' in values or
            'recurrence_budget_id' in values
        ):
            self.filtered(lambda record: record.recurrence_type).generate_recurrence_budgets()
        return res

    # ====================================================== ACTION =============================================================

    def action_open_budgets(self):
        action = self.env["ir.actions.actions"]._for_xml_id("work_abc_management.action_work_budget")
        action['domain'] = [('id', 'in', self.work_budget_ids.ids)]
        return action

    def action_open_allocation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("work_abc_management.action_work_allocation")
        action['domain'] = [('finance_id', 'in', self.ids)]
        action['context'] = {
            'search_default_group_by_allocation_group': True,
            'default_finance_id': self.id, 
            'default_project_id': self.project_id.id,
            'expand': True
        }
        return action
    

