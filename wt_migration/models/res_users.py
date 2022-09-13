from odoo import models, fields, _
from odoo.addons.wt_sdk import token

class ResUsers(models.Model):
    _inherit = "res.users"

    def get_jira_token(self):
        return token.get_token("jira_" + str(self.login or self.partner_id.email), self)

    def set_jira_token(self, value):
        token.set_token("jira_" + str(self.login or self.partner_id.email), value, self)

    def token_exists(self):
        existing_token_users = self.env['res.users']
        for user in self:
            try:
                user.get_jira_token()
                existing_token_users |= user
            except:
                continue
        return existing_token_users

