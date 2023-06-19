from odoo import api, fields, models, _


class CloneToMigration(models.TransientModel):
    _name = 'clone.to.migration'
    _description = 'Clone To Migration'

    wt_migration_id = fields.Many2one('wt.migration', string='Migration', ondelete="cascade")
    project_id = fields.Many2one("wt.project", string="Project", domain="[('wt_migration_id', '=', wt_migration_id)]")
    epic_id = fields.Many2one("wt.issue", string="Epic", domain="[('project_id', '=', project_id), ('epic_ok', '=', True)]")
    sprint_id = fields.Many2one("agile.sprint", string="Sprint", domain="[('project_id', '=', project_id)]")
    label_ids = fields.Many2many("wt.label", string="Labels")
    auto_export = fields.Boolean(string="Export to Destination Server?")
    assignee_id = fields.Many2one("res.users", string="Assign To", domain="[('account_id','!=', False)]")
    priority_id = fields.Many2one("wt.priority", string="Priority", domain="[('wt_migration_id', '=', wt_migration_id)]")
    issue_ids = fields.Many2many('wt.issue', string="Issues")
    is_all_same = fields.Boolean(string="Is All Same?", compute="_compute_is_all_same")
    rule_template_id = fields.Many2one("wt.clone.rule", string="Clone Template")

    def confirm(self):
        self.ensure_one()
        self.issue_ids.action_clone_to_server(self.wt_migration_id, self)

    def _compute_is_all_same(self):
        for record in self:
            record.is_all_same = (len(record.mapped('issue_ids.wt_migration_id')) == 1)

    @api.onchange('wt_migration_id')
    def _onchange_wt_migration_id(self):
        if self.is_all_same and self.wt_migration_id:
            src_migration = self.mapped('issue_ids.wt_migration_id')
            dest_migration = self.wt_migration_id
            applicables = self.env['wt.clone.rule'].search([('src_migration_id', '=', src_migration.id), 
                                                            ('dest_migration_id', '=', dest_migration.id)])
            if applicables:
                self.rule_template_id = applicables[0]
                return {'domain': {'rule_template_id':[('id', 'in', applicables.ids)]}}
        self.rule_template_id = False