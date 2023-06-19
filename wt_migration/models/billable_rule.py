from odoo import models, api, fields, _
from odoo.osv.expression import AND


class BillableRule(models.Model):
    _inherit = "wt.billable.rule"

    wt_migration_ids = fields.Many2many("wt.migration", string="Migration")
    project_ids = fields.Many2many(domain="[['wt_migration_id','in', wt_migration_ids]]")

    def _prepare_applicable_domain(self):
        domain = super()._prepare_applicable_domain()
        if self.wt_migration_ids:
            domain = AND([domain,[['wt_migration_id', 'in', self.wt_migration_ids.ids]]])
        return domain

    @api.depends('project_ids', 'epic_ids', 'label_ids', 'status_ids', 'priority_ids', 'text_content', 'exclude_issue_ids', 'include_issue_ids', "wt_migration_ids")
    def _compute_applicable_domain(self):
        super()._compute_applicable_domain()