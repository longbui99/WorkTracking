import ast

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv.expression import OR, AND

from odoo.addons.work_abc_management.utils.xml_parser import template_to_markup

class WorkBudgetInvoice(models.Model):
    _name = "work.budget.invoice"
    _description = "Budget Invoice"
    _order = "invoice_date desc"
    _rec_name = "invoice_date"

    # name = fields.Char(string="Name")
    invoice_date = fields.Datetime(string="Invoiced Date", default=fields.Datetime.now(), required=True)
    invoice_hours = fields.Float(string="Invoiced Hours", required=True)
    invoice_amount = fields.Monetary(string="Amount")
    work_budget_id = fields.Many2one("work.budget", string="Budget", required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)
    last_invoice_date = fields.Datetime(string="Last Invoice Date", compute="_compute_previous_invoice", compute_sudo=True)
    previous_invoice_id = fields.Many2one("work.budget.invoice", compute="_compute_previous_invoice", compute_sudo=True)
    
    log_hours = fields.Float(string="Logged Hours", compute="_compute_logged_information", compute_sudo=True) 
    billable_rate = fields.Float(string="Bilable Rate", compute="_compute_logged_information", compute_sudo=True) 

    def compile_log_domain(self):
        self.ensure_one()
        if not self.work_budget_id:
            raise UserError("Cannot find budget for invoice")
        domain = ast.literal_eval(self.work_budget_id.applicable_domain)
        custom_domain = [('start_date', '<', self.invoice_date)]
        if self.last_invoice_date:
            custom_domain.append(('start_date', '>=', self.last_invoice_date))
        domain = AND([domain, custom_domain])
        return domain

    @api.depends('work_budget_id')
    def _compute_previous_invoice(self):
        self.mapped('work_budget_id.budget_invoice_ids')
        for invoice in self:
            previous_invoice_line = False
            last_invoice_date = False
            invoices = invoice.work_budget_id.budget_invoice_ids
            if invoices:
                for todo_invoice in invoices.sorted('invoice_date'):
                    if todo_invoice.id >= invoice.id:
                        break
                    previous_invoice_line = todo_invoice
                last_invoice_date = previous_invoice_line.invoice_date if previous_invoice_line else False
            invoice.previous_invoice_id = previous_invoice_line
            invoice.last_invoice_date = last_invoice_date

    def _compute_logged_information(self):
        TimeLogEnv = self.env['work.time.log'].sudo()
        for record in self:
            logs = TimeLogEnv.search(record.compile_log_domain())
            record.log_hours = sum(logs.mapped('duration_hrs'))
            record.billable_rate = round((record.invoice_hours /record.log_hours )*100, 2) if record.log_hours else 0

    def action_open_work_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("work_abc_management.action_work_time_log")
        action['domain'] = self.compile_log_domain()
        return action
        

class WorkBudget(models.Model):
    _name = "work.budget"
    _description = "Budget Planning"
    _order = 'sequence, id desc'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string="Active", default=True)
    description = fields.Text(string="Description")
    project_id = fields.Many2one("work.project", string="Project", required=True)
    finance_id = fields.Many2one("work.finance", string="Finance Analytic")
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company.id, required=True)
    amount = fields.Monetary(string="Amount")
    duration = fields.Float(string="Duration", required=True, default=0)
    alert_duration = fields.Float(string="Alert when", default=-1)
    applicable_domain = fields.Char(string="Applicable Domain", default="[['id','=',-1]]")
    readable_user_ids = fields.Many2many("res.users", "readable_budget_user_rel", string="Readable Users")
    editable_user_ids = fields.Many2many("res.users", "editable_budget_user_rel", string="Editable Users")

    duration_used = fields.Float(string="Used Duration", compute="_compute_current_duration_used", digits=(16, 2))
    duration_percent_used = fields.Float(string="Used Duration Percent", compute="_compute_current_duration_used", digits=(16, 2))
    log_count = fields.Integer(string="Log Counts", compute="_compute_current_duration_used")

    notified_duration = fields.Float(string="Notified Duration", default=0, digits=(16, 2))

    state = fields.Selection([('in_progress', "In Progress"), ('invoiced', 'Invoiced')],
                              string="State",
                              default='in_progress')
    
    notification_type = fields.Selection([
         ('email', 'Email')
    ], default="email", string="Method")

    budget_invoice_ids = fields.One2many("work.budget.invoice", "work_budget_id", string="Invoice")
    last_invoice_date = fields.Datetime(string="Last Invoice Date", compute="_compute_previous_invoice_date")

    @api.depends('project_id', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.project_id:
                record.display_name = f"[{record.project_id.project_key}] {record.project_id.project_name}, {record.name}"
            else:
                record.display_name = record.name
    
    def compile_applicable_domain(self):
        self.ensure_one()
        applicable_domain = ast.literal_eval(self.applicable_domain)
        if self.last_invoice_date or self._context.get('ignore_last_date'):
            applicable_domain = AND([applicable_domain, [('start_date', '>', self.last_invoice_date)]])
        return applicable_domain

    def get_invoiced_duration(self):
        self.ensure_one()
        return sum(self.mapped('budget_invoice_ids.invoice_hours'))

    @api.depends('applicable_domain')
    def _compute_current_duration_used(self):
        TimeLogEnv = self.env['work.time.log'].sudo()
        for budget in self:
            invoiced_hours = budget.get_invoiced_duration()
            logs = TimeLogEnv.search(budget.compile_applicable_domain())
            budget.duration_used = sum(logs.mapped('duration_hrs')) + invoiced_hours
            budget.duration_percent_used = round((budget.duration_used / budget.duration)*100, 2) if budget.duration else 0
            total_logs = TimeLogEnv.search(budget.with_context(ignore_last_date=True).compile_applicable_domain())
            budget.log_count = len(total_logs)

    @api.depends('budget_invoice_ids')
    def _compute_previous_invoice_date(self):
        self.mapped('budget_invoice_ids')
        for budget in self:
            last_invoice = budget.budget_invoice_ids[:1]
            budget.last_invoice_date = last_invoice.invoice_date if last_invoice else False

    # ====================================================== ACTION =============================================================

    def action_open_logs(self):
        domain = []
        for budget in self:
            domain = OR([domain, ast.literal_eval(budget.applicable_domain)])
        action = self.env["ir.actions.actions"]._for_xml_id("work_abc_management.action_work_time_log")
        action['domain'] = domain
        return action

    def action_invoiced(self):
        self.write({'state': 'invoiced'})

    def action_draft(self):
        self.write({'state': 'in_progress'})

    def _action_send_notification_email(self):
        self.ensure_one()
        partners = (self.editable_user_ids | self.readable_user_ids | self.create_uid).partner_id
        self.message_subscribe(partner_ids=partners.ids)
        args = {
            'budget': self,
        }
        odoobot = self.env.ref('base.user_root')
        template = self.env.ref('work_abc_management.budget_notification_email').read()[0]
        html_markup = template_to_markup(self.env, template, **args)
        subject = f"Budget {self.name}, {self.duration_percent_used}% Notification"
        mail_message = self.env['mail.thread'].sudo().with_context(mail_notify_force_send=True).message_notify(
            subject=subject,
            body=str(html_markup),
            author_id=odoobot.id,
            partner_ids=partners.ids,
            email_layout_xmlid='work_abc_management.message_budget_notification'
        )
        self.message_post(body=html_markup)

    def action_send_notification(self):
        self.ensure_one()
        if self.notification_type == "email":
            self._action_send_notification_email()

    # ====================================================== CLASS METHOD =======================================================

    @api.model
    def _cron_notification(self):
        budgets = self.env['work.budget'].search([('state', '!=', 'invoiced'), ('notification_type', '!=', False)])
        budgets.mapped('log_count')
        for budget in budgets:
            if not budget.notified_duration and budget.duration_used > budget.alert_duration:
                budget.action_send_notification()
                budget.notified_duration = budget.duration_used
            elif budget.duration_used >= budget.duration and budget.duration_used != budget.notified_duration:
                budget.action_send_notification()
                budget.notified_duration = budget.duration_used
