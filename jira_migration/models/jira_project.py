from odoo import api, fields, models, _

class JiraProject(models.Model):
    _inherit = "jira.project"

    jira_migration_id = fields.Many2one("jira.migration", string="Jira Migration Credentials")
    last_update = fields.Datetime("Last Update Cron")

    @api.model
    def cron_fetch_ticket(self, load_create=True):
        if not self:
            self = self.search([])
        for project in self:
            user_ids = []
            if project.jira_migration_id:
                user_ids = project.jira_migration_id.admin_user_ids.ids
            if len(user_ids) == 0:
                user_ids = project.allowed_user_ids.ids
            access_token = self.env['hr.employee'].search(
                [('user_id', 'in', user_ids), 
                ('jira_private_key', '!=', False)], order='is_jira_admin desc').mapped(
                'jira_private_key')
            if any(access_token) and project.jira_migration_id:
                project.jira_migration_id.update_project(project, access_token[0])

    def reset_state(self):
        for record in self:
            record.last_update = False