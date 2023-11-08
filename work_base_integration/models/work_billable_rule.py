from odoo import models, api, fields, _
from odoo.osv.expression import AND


class BillableRule(models.Model):
    _inherit = "work.billable.rule"

    host_ids = fields.Many2many("work.base.integration", string="Host")
    project_ids = fields.Many2many(domain="[['host_id','in', host_ids]]")

    def _prepare_applicable_domain(self):
        domain = super()._prepare_applicable_domain()
        if self.host_ids:
            domain = AND([domain,[['host_id', 'in', self.host_ids.ids]]])
        return domain

    @api.depends('project_ids', 'epic_ids', 'label_ids', 'status_ids', 'priority_ids', 'text_content', 'exclude_task_ids', 'include_task_ids', "host_ids")
    def _compute_applicable_domain(self):
        super()._compute_applicable_domain()