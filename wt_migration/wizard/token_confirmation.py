from logging import exception
from urllib.parse import uses_relative
from odoo import models, fields, exceptions, _

class TokenConfirmation(models.TransientModel):
    _name = 'token.confirmation'
    _description = "Token Confirmation"

    employee_id = fields.Many2one("hr.employee", string="Employee")
    token = fields.Char(string="Token", required=True)

    def action_confirm(self):
        if not self.employee_id.user_id:
            raise exceptions.UserError("Please link the specific user for employee")
        elif self.employee_id.user_id.id != self.env.user.id:
            raise exceptions.UserError("Cannot update token on other user")
        
        self.employee_id.update_token(self.token)
        self.update({'token': True})
        