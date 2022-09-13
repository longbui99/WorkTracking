from odoo import fields, models, _

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    is_wt_admin = fields.Boolean(string="Admin?", tracking=True)
    auto_export_work_log = fields.Boolean(string='Auto Export Logs', tracking=True)
    auto_remove_access = fields.Boolean(string="Auto Remove Access", default=True)
    maximum_connection = fields.Integer(string="Maximum Extension Connection", default=4)

    def action_reset_extension_token(self):
        self.ensure_one()
        if self.user_id:
            self.env['user.access.code'].sudo().search([('uid', '=', self.env.user.id)]).unlink()

    def action_update_token(self):
        action = self.env["ir.actions.actions"]._for_xml_id("wt_migration.token_confirmation_action_form")
        action['context'] = {'default_employee_id': self.id} 
        return action