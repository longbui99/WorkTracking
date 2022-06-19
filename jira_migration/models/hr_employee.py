from odoo import api, fields, models, _


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    jira_private_key = fields.Char(string='Access Token')
    is_jira_admin = fields.Boolean(string="Admin?", tracking=True)
    auto_export_work_log = fields.Boolean(string='Auto Export Logs', tracking=True)
    auto_remove_access = fields.Boolean(string="Auto Remove Access", default=True)
    maximum_connection = fields.Integer(string="Maximum Extension Connection", default=4)

    def action_reset_token(self):
        self.ensure_one()
        if self.user_id:
            self.env['user.access.code'].sudo().search([('uid', '=', self.env.user.id)]).unlink()
