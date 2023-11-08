import json

from odoo import models, api, fields, _
from odoo.osv.expression import AND


class BillableRule(models.Model):
    _name = "work.billable.rule"
    _description = "Billable Rule"
    _order = 'sequence desc, id desc'

    sequence = fields.Integer(string="Sequence")
    rule_type = fields.Selection([
        ('non-bill', 'Non-billable'),
        ('bill', 'Billable')
        ],
        string="Rule Type",
        required=True,
        default='non-bill'
    )
    name = fields.Char(string="Name", required=True)
    project_ids = fields.Many2many("work.project", 'billable_rule_project', string="Projects")
    epic_ids = fields.Many2many("work.task", 'billable_rule_epic', string="Epics", domain="[['project_id','in', project_ids], ['epic_ok', '=', True]]")
    label_ids = fields.Many2many("work.label", 'billable_rule_label', string="Labels")
    status_ids = fields.Many2many("work.status", 'billable_rule_status', string="Statuses")
    priority_ids = fields.Many2many("work.priority", 'billable_rule_priority', string="Priority")
    text_content = fields.Char(string="Display Name")

    exclude_task_ids = fields.Many2many("work.task", 'billable_rule_excluding_task', string="Exclude Tasks", domain="[['project_id','in', project_ids]]")
    include_task_ids = fields.Many2many("work.task", 'billable_rule_including_task', string="Include Tasks", domain="[['project_id','in', project_ids]]")

    applicable_task_ids = fields.Many2many(comodel_name="work.task", store=False, compute="_compute_applicable_task_ids")
    new_task_ids = fields.Many2many(comodel_name="work.task", store=False, compute="_compute_applicable_task_ids")

    applicable_domain = fields.Char(string="Applicable Domain", compute="_compute_applicable_domain", store=True)
    start_date = fields.Datetime(string="Start Timestamp")
    end_date = fields.Datetime(string="End Timestamp")

    def _prepare_applicable_domain(self):
        self.ensure_one()
        domain = []
        if self.project_ids:
            domain = AND([domain,[['project_id', 'in', self.project_ids.ids]]])
        if self.epic_ids:
            domain = AND([domain,[['epic_id', 'in', self.epic_ids.ids]]])
        if self.label_ids:
            domain = AND([domain,[['label_ids', 'in', self.label_ids.ids]]])
        if self.status_ids:
            domain = AND([domain,[['status_id', 'in', self.status_ids.ids]]])
        if self.priority_ids:
            domain = AND([domain,[['priority_id', 'in', self.priority_ids.ids]]])
        if self.text_content:
            domain = AND([domain,[['task_name', 'ilike', self.text_content]]])
        if self.exclude_task_ids:
            domain = AND([domain,[['id', 'not in', self.exclude_task_ids.ids]]])
        if self.include_task_ids:
            domain = AND([domain,[['id', 'in', self.include_task_ids.ids]]])
        if self.start_date:
            domain = AND([domain,[['create_date', '>=', self.start_date.strftime("%Y-%m-%d")]]])
        if self.end_date:
            domain = AND([domain,[['create_date', '<', self.end_date.strftime("%Y-%m-%d")]]])
        return domain
    
    @api.depends('project_ids', 'epic_ids', 'label_ids', 'status_ids', 'priority_ids', 'text_content', 'exclude_task_ids', 'include_task_ids')
    def _compute_applicable_domain(self):
        for record in self:
            domain = json.dumps(record._prepare_applicable_domain())
            record.applicable_domain = domain

    def apply_nonbillable_rule(self):
        self.ensure_one()
        domain = self._prepare_applicable_domain()
        tasks = self.env['work.task'].search(domain)
        tasks.write({'billable_state': self.rule_type})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Apply Successfully.'),
            }
        }