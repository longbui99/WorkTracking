from odoo import fields, models, _


class HREmployee(models.AbstractModel):
    _inherit = 'hr.employee.base'

    is_wt_admin = fields.Boolean(string="Admin?")
    auto_export_work_log = fields.Boolean(string='Auto Export Logs')

    def action_update_token(self):
        action = self.env["ir.actions.actions"]._for_xml_id("wt_migration.token_confirmation_action_form")
        action['context'] = {'default_employee_id': self.id}
        return action

    def update_token(self, token):
        self.user_id and self.user_id.set_jira_token(token)
