from odoo import api, fields, models, _


class CloneToHost(models.TransientModel):
    _name = 'clone.to.host'
    _description = 'Clone To Host'

    host_id = fields.Many2one('work.base.integration', string='Host', ondelete="cascade")
    company_id = fields.Many2one("res.company", string="Company", related="host_id.company_id")
    project_id = fields.Many2one("work.project", string="Project", domain="[('host_id', '=', host_id)]")
    epic_id = fields.Many2one("work.task", string="Epic", domain="[('project_id', '=', project_id), ('epic_ok', '=', True)]")
    sprint_id = fields.Many2one("agile.sprint", string="Sprint", domain="[('project_id', '=', project_id)]")
    label_ids = fields.Many2many("work.label", string="Labels")
    auto_export = fields.Boolean(string="Export to Destination Server?")
    assignee_id = fields.Many2one("res.users", string="Assign To")
    priority_id = fields.Many2one("work.priority", string="Priority", domain="[('host_id', '=', host_id)]")
    task_type_id = fields.Many2one("work.type", string="Type", domain="[('project_ids', '=', project_id)]")
    task_ids = fields.Many2many('work.task', string="Tasks")
    prefix = fields.Char(string="Prefix")
    is_all_same = fields.Boolean(string="Is All Same?", compute="_compute_is_all_same")
    rule_template_id = fields.Many2one("work.clone.rule", string="Clone Template")

    def confirm(self):
        self.ensure_one()
        return self.task_ids.action_clone_to_host(self.host_id, self)

    def _compute_is_all_same(self):
        for record in self:
            record.is_all_same = (len(record.mapped('task_ids.host_id')) == 1)

    def get_template_recommendation(self, src_host, destination_host):
        self.ensure_one()
        task_env = self.env['work.task']
        value = task_env.prepare_value_for_cloned_task(task_env, self, destination_host, False)
        sample_task = task_env.new(value)

        epics = self.mapped('task_ids.epic_id')
        if len(epics) == 1:
            sample_task.epic_id = epics.id

        types = self.mapped('task_ids.task_type_id')
        if len(types) == 1:
            sample_task.task_type_id = types.id

        projects = self.mapped('task_ids.project_id')
        if len(projects) == 1:
            sample_task.project_id = projects.id

        priorities = self.mapped('task_ids.priority_id')
        if len(projects) == 1:
            sample_task.priority_id = priorities.id

        template = src_host.with_context(force_clone_template_rule=self.rule_template_id).load_clone_template(self.host_id, self)
        task_env.map_template_to_values(sample_task, value, template, 'task_type_id', 'types')
        task_env.map_template_to_values(sample_task, value, template, 'status_id', 'statuses')
        task_env.map_template_to_values(sample_task, value, template, 'project_id', 'projects')
        task_env.map_template_to_values(sample_task, value, template, 'epic_id', 'epics')
        task_env.map_template_to_values(sample_task, value, template, 'priority_id', 'priorities')
        sample_task.update(value)

        label_ids = set(self.task_ids[0].label_ids.ids)
        if all(not (set(task.label_ids.ids) - label_ids) for task in self.task_ids[1:]):
            sample_task.label_ids = self.task_ids[0].label_ids

        self.project_id = sample_task.project_id
        self.epic_id = sample_task.epic_id
        self.priority_id = sample_task.priority_id
        self.task_type_id = sample_task.task_type_id
        self.label_ids = sample_task.label_ids

    def erase_selection(self):
        self.rule_template_id = False
        self.project_id = False
        self.epic_id = False
        self.priority_id = False
        self.task_type_id = False
        self.label_ids = False

    @api.onchange('host_id')
    def _onchange_host_id(self):
        if self.is_all_same and self.host_id:
            domain = []
            src_host = self.mapped('task_ids.host_id')
            dest_host = self.host_id
            if not self.rule_template_id and not self.env.context.get('bypass_template_fetching'):
                applicables = self.env['work.clone.rule'].search([('src_host_id', '=', src_host.id), 
                                                                ('dest_host_id', '=', dest_host.id)])
                if applicables:
                    self.rule_template_id = applicables[0]
                    domain = [('id', 'in', applicables.ids)]
            if self.rule_template_id:
                self.get_template_recommendation(src_host, dest_host)
            return {'domain': {'rule_template_id': domain}}
            
        self.erase_selection()
    
    @api.onchange('rule_template_id')
    def _onchange_rule_template_id(self):
        self.with_context(bypass_template_fetching=True)._onchange_host_id()