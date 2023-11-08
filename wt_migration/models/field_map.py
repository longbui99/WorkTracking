from odoo import models, api, fields, _


class FieldMap(models.Model):
    _name = "wt.field.map"
    _description = "Field Mapping"

    migration_id = fields.Many2one('wt.migration', string="Migration", required=True, ondelete="cascade")
    key = fields.Selection([
        ('issue_status', 'Issue Status'),
        ('issue_story_point', 'Issue Story Point'),
        ('issue_estimate_hour', 'Issue Estimate Hour'),
        ('issue_assignee', 'Issue Assignee'),
        ('issue_tester', 'Issue Tester'),
        ('issue_project', 'Issue Project'),
        ('issue_type', 'Issue Type'),
        ('issue_summary', 'Issue Summary'),
        ('issue_acceptance_criteria', 'Issue Checklists'),
        ('issue_created_date', 'Issue Create Date'),
        ('issue_labels', 'Issue Labels'),
        ('sprint', 'Sprint'),
        ('priority', 'priority'),
        ('checklist', 'Checklist')
    ])
    value = fields.Char(string="Value")
    template_id = fields.Many2one("wt.migration.map.template", string="Template")
    field_id = fields.Many2one("ir.model.fields", string="For Field")
    type = fields.Selection([('sdk', 'SDK Import'), ('field_map', 'Field Map')], string="Type", default="sdk")

    @api.model
    def create_template(self, migration):
        template = {
            'priority': 'priority',
            'issue_status': 'status',
            'issue_story_point': 'customfield_10028',
            'issue_estimate_hour': 'customfield_10056',
            'issue_assignee': 'assignee',
            'issue_tester': 'customfield_11101',
            'issue_project': 'project',
            'issue_type': 'issuetype',
            'issue_summary': 'summary',
            'issue_acceptance_criteria': 'customfield_10034',
            'issue_created_date': 'created',
            'issue_labels': 'labels',
            'sprint': 'customfield_10020',
            'checklist': 'customfield_10035'
        }
        values = []
        for key, value in template.items():
            values.append({
                'migration_id': migration.id,
                'key': key,
                'value': value,
                'type': 'sdk'
            })

        if not migration.template_id:
            migration.template_id = self.env['wt.migration.map.template'].create({})

        values.extend([
            {
                'field_id': self.env.ref('project_management.field_wt_issue__issue_name').id,
                'value': 'summary',
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            },
            {
                'field_id': self.env.ref('project_management.field_wt_issue__project_id').id,
                'value': 'project',
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            },
            {
                'field_id': self.env.ref('project_management.field_wt_issue__label_ids').id,
                'value': 'labels',
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            },
            {
                'field_id': self.env.ref('project_management.field_wt_issue__issue_type_id').id,
                'value': 'issuetype',
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            },
            {
                'field_id': self.env.ref('project_management.field_wt_issue__description').id,
                'value': 'description',
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            },
            {
                'field_id': self.env.ref('project_management.field_wt_issue__epic_id').id,
                'value': False,
                'migration_id': migration.id,
                'template_id': migration.template_id.id
            }
        ])

        self.create(values)
class MigrationMapTemplate(models.Model):
    _name = "wt.migration.map.template"
    _description = "Migration Map Template"

    field_ids = fields.One2many("wt.field.map", 'template_id', string="Fields")
    