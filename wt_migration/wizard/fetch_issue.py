from odoo import models, api, fields, _
from odoo.exceptions import UserError

class FetchIssue(models.Model):
    _name = "wt.fetch.issue"
    _description = "WT fetch issue by domain"
    _rec_name = "query"

    query = fields.Char(string="Query", required=True)
    migration_id = fields.Many2one("wt.migration", string="Host", compute="_compute_suitable_migration_id")
    user_id = fields.Many2one("res.users", string="Load As", groups="base.group_system")

    @api.depends('query')
    def _compute_suitable_migration_id(self):
        migrations = self.env['wt.migration']
        for record in self:
            record.migration_id, __ = migrations.get_host_and_issue_by_query(record.query)

    def action_load(self):
        self.ensure_one()
        if not self.migration_id:
            raise UserError(_("Cannot find suitable Host for this link!"))
        if self.user_id and self.env.user.has_group('base.group_system'):
            self = self.with_user(self.user_id)
        self.migration_id.query_candidate_issue(self.query)
        