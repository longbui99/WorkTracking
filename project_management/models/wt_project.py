from odoo import api, fields, models, _


class WtProject(models.Model):
    _name = "wt.project"
    _description = "Task Project"
    _order = 'pin desc, sequence asc, create_date desc'
    _rec_name = "name"

    pin = fields.Integer(string='Pin')
    sequence = fields.Integer(string='Sequence')
    project_name = fields.Char(string='Name', required=True)
    project_key = fields.Char(string='Project Key')
    allowed_user_ids = fields.Many2many('res.users', 'res_user_wt_project_rel_1', 'wt_project_id', 'res_users_id',
                                        string='Allowed Users')
    allowed_manager_ids = fields.Many2many('res.users', 'res_user_wt_project_rel_2', 'wt_project_id', 'res_users_id',
                                           string='Managers')
    issue_ids = fields.One2many('wt.issue', 'project_id', string='Issues')
    chain_work_ids = fields.One2many("wt.chain.work.session", "project_id", "Chain Works")
    board_ids = fields.One2many('board.board', 'project_id', string="Boards")
    sprint_ids = fields.One2many('agile.sprint', 'project_id', string="Sprints")
    personal_id = fields.Many2one("res.users", string="Personal Board User")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    name = fields.Char(string="Name", compute="_compute_name", store=True)

    @api.depends('project_name', 'project_key')
    def _compute_name(self):
        for project in self:
            project.name = '%s - %s' % (project.project_key, project.project_name)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if len(name):
            args = ['|', ('project_name', 'ilike', name), ('project_key', 'ilike', name)]
        print(args)
        return super().name_search(name, args, operator, limit)

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

    def action_export_record(self, workbook):
        self.ensure_one()
        header_format = workbook.add_format({
            'text_wrap': True,
            'valign': 'top',
            'bold': True,
            'align': 'center'
        })
        text_format = workbook.add_format({
            'text_wrap': True,
            'valign': 'top'
        })
        sheet = workbook.add_worksheet(self.display_name)
        sheet.write(0, 0, self.display_name, header_format)
        sheet.write(1, 0, self.project_key, text_format)
        return workbook

    def create(self, values):
        if 'allowed_manager_ids' in values:
            values['allowed_user_ids'] = values['allowed_manager_ids']
        return super().create(values)

    def write(self, values):
        res = super().write(values)
        if len(values.get('allowed_manager_ids', [])):
            new_record = self.new(values)
            for record in self:
                new_users = new_record.allowed_manager_ids - record.allowed_user_ids
                if (new_users):
                    record.allowed_user_ids = [fields.Command.link(user._origin.id) for user in new_users]
        return res

    def gather_personal_project(self):
        project = self.search([('personal_id', '=', self.env.user.id)])
        if not project:
            board_name = self.env.user.name or self.env.user.employee_id.name
            project = self.create({
                'project_name': "PERSONAL: " + board_name,
                'project_key': "PER" + "".join([x[0] for x in board_name.split(' ') if len(x)]),
                'personal_id': self.env.user.id
            })
        return project