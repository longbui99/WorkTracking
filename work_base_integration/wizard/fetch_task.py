from odoo import models, api, fields, _
from odoo.exceptions import UserError

class FetchTask(models.Model):
    _name = "work.fetch.task"
    _description = "WT fetch task by domain"
    _rec_name = "query"

    query = fields.Char(string="Query", required=True)
    host_id = fields.Many2one("work.base.integration", string="Host", compute="_compute_suitable_host_id")
    user_id = fields.Many2one("res.users", string="Load As", groups="base.group_system")

    @api.depends('query')
    def _compute_suitable_host_id(self):
        hosts = self.env['work.base.integration']
        for record in self:
            record.host_id, __ = hosts.get_host_and_task_by_query(record.query)

    def action_load(self):
        self.ensure_one()
        if not self.host_id:
            raise UserError(_("Cannot find suitable Host for this link!"))
        if self.user_id and self.env.user.has_group('base.group_system'):
            self = self.with_user(self.user_id)
        self.host_id.query_candidate_task(self.query)
        