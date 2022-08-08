from odoo import api, fields, models, _


class WtProject(models.Model):
    _name = "wt.project"
    _description = "Task Project"
    _order = 'pin desc, sequence asc, create_date desc'
    _rec_name = 'project_key'

    pin = fields.Integer(string='Pin')
    sequence = fields.Integer(string='Sequence')
    project_name = fields.Char(string='Name', required=True)
    project_key = fields.Char(string='Project Key')
    allowed_user_ids = fields.Many2many('res.users', string='Allowed Users')
    allowed_manager_ids = fields.Many2many('res.users', 'res_user_wt_project_rel_2', string='Managers')
    issue_ids = fields.One2many('wt.issue', 'project_id', string='Issues')
    wt_migration_id = fields.Many2one("wt.migration", string="Task Migration Credentials")
    chain_work_ids = fields.One2many("wt.chain.work.session", "project_id", "Chain Works")
    board_ids = fields.One2many('board.board', 'project_id', string="Boards")
    sprint_ids = fields.One2many('agile.sprint', 'project_id', string="Sprints")

    def fetch_user_from_issue(self):
        for record in self:
            user_ids = self.env['wt.issue'] \
                .search([('project_id', '=', record.id)]) \
                .mapped('time_log_ids').mapped('user_id')
            create_new_users = user_ids.filtered(lambda r: r.id not in record.allowed_user_ids.ids)
            record.allowed_user_ids = create_new_users.mapped(lambda r: (4, r.id, False))

    @api.model
    def cron_fetch_user_from_issue(self):
        self.search([]).fetch_user_from_issue()

    def action_start_kick_off(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.chain_work_base_action")
        action["context"] = {
            'default_project_id': self.id,
        }
        return action

    def action_start_latest_chain(self):
        self.ensure_one()
        my_chain_work_ids = self.chain_work_ids.filtered(
            lambda r: r.create_uid == self.env.user and r.state != "logged")
        if my_chain_work_ids:
            action = self.env["ir.actions.actions"]._for_xml_id("project_management.log_work_action_form_mobile_view")
            action["res_id"] = my_chain_work_ids[0].id
            action["context"] = {"mobile": True}
            return action

    def action_open_sprint(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id("project_management.action_wt_active_sprint")
        action["domain"] = [('project_id', '=', self.id)]
        return action
