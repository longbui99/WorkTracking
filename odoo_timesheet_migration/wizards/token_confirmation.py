from logging import exception
from urllib.parse import uses_relative
from odoo import models, fields, exceptions, api, _

class TokenConfirmation(models.TransientModel):
    _inherit = "token.confirmation"

    login = fields.Char(string="Login")
    login_required = fields.Boolean(compute="_compute_login_required")

    def action_confirm(self):
        if self.migration_id.migration_type == "odoo":
            self.token = self.migration_id.merge_odoo_credential(self.login, self.token)
        return super().action_confirm()

    @api.depends('migration_id')
    def _compute_login_required(self):
        for record in self:
            record.login_required = self.migration_id.migration_type == "odoo" if self.migration_id else False
