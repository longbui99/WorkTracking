import ast

from odoo import api, fields, models, _
from odoo.osv.expression import OR

from odoo.addons.project_management.utils.xml_parser import template_to_markup


class WtBudget(models.Model):
    _name = "wt.budget"
    _description = "Budget Planning"
    _order = 'sequence, id desc'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string="Active", default=False)
    description = fields.Text(string="Description")
    project_id = fields.Many2one("wt.project", string="Project", required=True)
    finance_id = fields.Many2one("wt.finance", string="Finance Analytic")
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, states={'in_progress': [('readonly', False)]},
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

    def name_get(self):
        ret_list = []
        for record in self:
            if record.project_id:
                name = f"[{record.project_id.project_key}] {record.project_id.project_name}, {record.name}"
            else:
                name = record.name
            ret_list.append((record.id, name))
        return ret_list

    @api.depends('applicable_domain')
    def _compute_current_duration_used(self):
        TimeLogEnv = self.env['wt.time.log'].sudo()
        for budget in self:
            logs = TimeLogEnv.search(ast.literal_eval(budget.applicable_domain))
            budget.duration_used = sum(logs.mapped('duration_hrs'))
            budget.duration_percent_used = round((budget.duration_used / budget.duration)*100, 2)
            budget.log_count = len(logs)

    # ====================================================== ACTION =============================================================

    def action_open_logs(self):
        domain = []
        for budget in self:
            domain = OR([domain, ast.literal_eval(budget.applicable_domain)])
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.action_wt_time_log")
        action['domain'] = domain
        return action

    def action_invoiced(self):
        self.write({'state': 'invoiced'})

    def action_draft(self):
        self.write({'state': 'in_progress'})

    def _action_send_notification_email(self):
        self.ensure_one()
        partners = (self.editable_user_ids | self.readable_user_ids | self.create_uid).partner_id
        args = {
            'budget': self,
        }
        odoobot = self.env.ref('base.user_root')
        template = self.env.ref('project_management.budget_notification_email').read()[0]
        html_markup = template_to_markup(self.env, template, **args)
        subject = f"Budget {self.name}, {self.duration_percent_used}% Notification"
        mail_message = self.env['mail.thread'].sudo().with_context(mail_notify_force_send=True).message_notify(
            subject=subject,
            body=str(html_markup),
            author_id=odoobot.id,
            partner_ids=partners.ids,
            email_layout_xmlid='project_management.message_budget_notification'
        )

    def action_send_notification(self):
        self.ensure_one()
        if self.notification_type == "email":
            self._action_send_notification_email()

    # ====================================================== CLASS METHOD =======================================================

    @api.model
    def _cron_notification(self):
        budgets = self.env['wt.budget'].search([('state', '!=', 'invoiced'), ('notification_type', '!=', False)])
        budgets.mapped('log_count')
        for budget in budgets:
            if budget.notified_duration and \
                budget.notified_duration < budget.duration and \
                    budget.duration_used >= budget.duration:
                    budget.action_send_notification()
                    budget.notified_duration = budget.duration_used
            elif budget.duration_used >= budget.alert_duration:
                    budget.action_send_notification()
                    budget.notified_duration = budget.duration_used
