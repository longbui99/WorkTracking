from odoo import models, api, fields, _
from odoo.exceptions import UserError

class FetchIssue(models.Model):
    _name = "wt.fetch.issue"
    _description = "WT fetch issue by domain"
    _rec_name = "query"

    query = fields.Char(string="Query", required=True)
    migration_id = fields.Many2one("wt.migration", string="Host", compute="_compute_suitable_migration_id")

    @api.depends('query')
    def _compute_suitable_migration_id(self):
        migrations = self.env['wt.migration']
        for record in self:
            record.migration_id, __ = migrations.get_host_and_issue_by_query(record.query)

    def action_load(self):
        self.ensure_one()
        if not self.migration_id:
            raise UserError(_("Cannot find suitable Host for this link!"))
        self.migration_id.query_candidate_issue(self.query)
        