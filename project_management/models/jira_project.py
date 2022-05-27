from odoo import api, fields, models, _


class JiraProject(models.Model):
    _name = "jira.project"
    _description = "JIRA Project"
    _order = 'pin desc, sequence asc, create_date desc'
    _rec_name = 'project_key'

    pin = fields.Integer(string='Pin')
    sequence = fields.Integer(string='Sequence')
    project_name = fields.Char(string='Name', required=True)
    project_key = fields.Char(string='Project Key')
    allowed_user_ids = fields.Many2many('res.users', string='Allowed Users')
    allowed_manager_ids = fields.Many2many('res.users', 'res_user_jira_project_rel_2', string='Managers')
    ticket_ids = fields.One2many('jira.ticket', 'project_id', string='Tickets')
    jira_migration_id = fields.Many2one("jira.migration", string="Jira Migration Credentials")

    def fetch_user_from_ticket(self):
        for record in self:
            user_ids = self.env['jira.ticket'] \
                .search([('project_id', '=', record.id)]) \
                .mapped('time_log_ids').mapped('user_id')
            record.allowed_user_ids = [fields.Command.set(user_ids.ids)]

    @api.model
    def cron_fetch_user_from_ticket(self):
        self.search([]).fetch_user_from_ticket()
