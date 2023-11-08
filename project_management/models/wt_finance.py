from datetime import datetime

from odoo import api, fields, models, _


class WtFinance(models.Model):
    _name = "wt.finance"
    _description = "Finance Analytic"
    _order = 'sequence, id desc'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company.id, required=True)
    wt_budget_ids = fields.One2many("wt.budget", 'finance_id', string="Budgets")
    duration = fields.Float(string="Total Duration", compute='_compute_current_duration_used')
    duration_used = fields.Float(string="Total Used Duration", compute="_compute_current_duration_used")
    duration_percent_used = fields.Float(string="Duration Used Percent", compute="_compute_current_duration_used")
    budget_count = fields.Integer(string="Budget Count", compute="_compute_current_duration_used")
    amount = fields.Float(string="Total Amount", compute="_compute_current_duration_used")
    project_id = fields.Many2one("wt.project", string="Project", required=True)
    access_user_ids = fields.Many2many("res.users", "access_finance_user_rel", string="Accessible Users")
    due_date = fields.Datetime(string="End Date", default=lambda self: fields.Datetime.now())

    def _compute_current_duration_used(self):
        self.mapped('wt_budget_ids.duration_used')
        for finance in self:
            finance.duration = sum(finance.wt_budget_ids.mapped('duration'))
            finance.duration_used = sum(finance.wt_budget_ids.mapped('duration_used'))
            finance.duration_percent_used = 100*finance.duration_used/finance.duration if finance.duration else 0
            finance.budget_count = len(finance.wt_budget_ids)
            finance.amount = sum(finance.wt_budget_ids.mapped('amount'))

    # ====================================================== ACTION =============================================================

    def action_open_budgets(self):
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.action_wt_budget")
        action['domain'] = [('id', 'in', self.wt_budget_ids.ids)]
        return action

    def action_open_allocation(self):
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.action_wt_allocation")
        action['domain'] = [('finance_id', 'in', self.ids)]
        action['context'] = {'default_finance_id': self.id, 'default_project_id': self.project_id.id}
        return action