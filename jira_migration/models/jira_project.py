from odoo import api, fields, models, _


class JiraProject(models.Model):
    _inherit = "jira.project"

    jira_migration_id = fields.Many2one("jira.migration", string="Jira Migration Credentials")
    last_update = fields.Datetime("Last Update Cron")

    @api.model
    def cron_fetch_ticket(self, load_create=True):
        for project in self.search([]):
            access_token = self.env['hr.employee'].search(
                [('user_id', 'in', project.allowed_user_ids.ids), ('jira_private_key', '!=', False)]).mapped(
                'jira_private_key')
            if any(access_token):
                project.jira_migration_id.with_context().update_project(project, access_token[0])

