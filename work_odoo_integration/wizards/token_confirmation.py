from logging import exception
from urllib.parse import uses_relative
from odoo import models, fields, exceptions, api, _

class TokenConfirmation(models.TransientModel):
    _inherit = "token.confirmation"

    login = fields.Char(string="Login")
    login_required = fields.Boolean(compute="_compute_login_required")

    def action_confirm(self):
        if self._id._type == "odoo":
            self.token = self._id.merge_odoo_credential(self.login, self.token)
        return super().action_confirm()

    @api.depends('host_id')
    def _compute_login_required(self):
        for record in self:
            record.login_required = self._id._type == "odoo" if self._id else False
