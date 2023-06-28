from odoo import api, fields, models, _


class CloneToMigration(models.TransientModel):
    _name = 'clone.to.migration'
    _description = 'Clone To Migration'

    wt_migration_id = fields.Many2one('wt.migration', string='Migration', ondelete="cascade")
    company_id = fields.Many2one("res.company", string="Company", related="wt_migration_id.company_id")
    project_id = fields.Many2one("wt.project", string="Project", domain="[('wt_migration_id', '=', wt_migration_id)]")
    epic_id = fields.Many2one("wt.issue", string="Epic", domain="[('project_id', '=', project_id), ('epic_ok', '=', True)]")
    sprint_id = fields.Many2one("agile.sprint", string="Sprint", domain="[('project_id', '=', project_id)]")
    label_ids = fields.Many2many("wt.label", string="Labels")
    auto_export = fields.Boolean(string="Export to Destination Server?")
    assignee_id = fields.Many2one("res.users", string="Assign To", domain="[('account_id','!=', False)]")
    priority_id = fields.Many2one("wt.priority", string="Priority", domain="[('wt_migration_id', '=', wt_migration_id)]")
    issue_type_id = fields.Many2one("wt.type", string="Type", domain="[('company_id', '=', company_id)]")
    issue_ids = fields.Many2many('wt.issue', string="Issues")
    prefix = fields.Char(string="Prefix")
    is_all_same = fields.Boolean(string="Is All Same?", compute="_compute_is_all_same")
    rule_template_id = fields.Many2one("wt.clone.rule", string="Clone Template")

    def confirm(self):
        self.ensure_one()
        return self.issue_ids.action_clone_to_server(self.wt_migration_id, self)

    def _compute_is_all_same(self):
        for record in self:
            record.is_all_same = (len(record.mapped('issue_ids.wt_migration_id')) == 1)

    def get_template_recommendation(self, src_migration, destination_migration):
        self.ensure_one()
        issue_env = self.env['wt.issue']
        value = issue_env.prepare_value_for_cloned_issue(issue_env, self, destination_migration, False)
        sample_issue = issue_env.new(value)

        epics = self.mapped('issue_ids.epic_id')
        if len(epics) == 1:
            sample_issue.epic_id = epics.id

        types = self.mapped('issue_ids.issue_type_id')
        if len(types) == 1:
            sample_issue.issue_type_id = types.id

        projects = self.mapped('issue_ids.project_id')
        if len(projects) == 1:
            sample_issue.project_id = projects.id

        priorities = self.mapped('issue_ids.priority_id')
        if len(projects) == 1:
            sample_issue.priority_id = priorities.id

        template = src_migration.with_context(force_clone_template_rule=self.rule_template_id).load_clone_template(self.wt_migration_id, self)
        issue_env.map_template_to_values(sample_issue, value, template, 'issue_type_id', 'types')
        issue_env.map_template_to_values(sample_issue, value, template, 'status_id', 'statuses')
        issue_env.map_template_to_values(sample_issue, value, template, 'project_id', 'projects')
        issue_env.map_template_to_values(sample_issue, value, template, 'epic_id', 'epics')
        issue_env.map_template_to_values(sample_issue, value, template, 'priority_id', 'priorities')
        sample_issue.update(value)

        label_ids = set(self.issue_ids[0].label_ids.ids)
        if all(not (set(issue.label_ids.ids) - label_ids) for issue in self.issue_ids[1:]):
            sample_issue.label_ids = self.issue_ids[0].label_ids

        self.project_id = sample_issue.project_id
        self.epic_id = sample_issue.epic_id
        self.priority_id = sample_issue.priority_id
        self.issue_type_id = sample_issue.issue_type_id
        self.label_ids = sample_issue.label_ids

    def erase_selection(self):
        self.rule_template_id = False
        self.project_id = False
        self.epic_id = False
        self.priority_id = False
        self.issue_type_id = False
        self.label_ids = False

    @api.onchange('wt_migration_id')
    def _onchange_wt_migration_id(self):
        if self.is_all_same and self.wt_migration_id:
            domain = []
            src_migration = self.mapped('issue_ids.wt_migration_id')
            dest_migration = self.wt_migration_id
            if not self.rule_template_id and not self.env.context.get('bypass_template_fetching'):
                applicables = self.env['wt.clone.rule'].search([('src_migration_id', '=', src_migration.id), 
                                                                ('dest_migration_id', '=', dest_migration.id)])
                if applicables:
                    self.rule_template_id = applicables[0]
                    domain = [('id', 'in', applicables.ids)]
            if self.rule_template_id:
                self.get_template_recommendation(src_migration, dest_migration)
            return {'domain': {'rule_template_id': domain}}
            
        self.erase_selection()
    
    @api.onchange('rule_template_id')
    def _onchange_rule_template_id(self):
        self.with_context(bypass_template_fetching=True)._onchange_wt_migration_id()