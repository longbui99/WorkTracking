from odoo import models, api, fields, _


class FieldMap(models.Model):
    _name = "work.field.map"
    _description = "Field Mapping"

    host_id = fields.Many2one('work.base.integration', string="Host", required=True, ondelete="cascade")
    key = fields.Selection([
        ('task_status', 'Task Status'),
        ('task_story_point', 'Task Story Point'),
        ('task_estimate_hour', 'Task Estimate Hour'),
        ('task_assignee', 'Task Assignee'),
        ('task_tester', 'Task Tester'),
        ('task_project', 'Task Project'),
        ('task_type', 'Task Type'),
        ('task_summary', 'Task Summary'),
        ('task_acceptance_criteria', 'Task Checklists'),
        ('task_created_date', 'Task Create Date'),
        ('task_labels', 'Task Labels'),
        ('sprint', 'Sprint'),
        ('priority', 'priority'),
        ('checklist', 'Checklist')
    ])
    value = fields.Char(string="Value")
    template_id = fields.Many2one("work.base.integration.map.template", string="Template")
    field_id = fields.Many2one("ir.model.fields", string="For Field")
    type = fields.Selection([('sdk', 'SDK Import'), ('field_map', 'Field Map')], string="Type", default="sdk")

    @api.model
    def create_template(self, host):
        template = {
            'priority': 'priority',
            'task_status': 'status',
            'task_story_point': 'customfield_10028',
            'task_estimate_hour': 'customfield_10056',
            'task_assignee': 'assignee',
            'task_tester': 'customfield_11101',
            'task_project': 'project',
            'task_type': 'issuetype',
            'task_summary': 'summary',
            'task_acceptance_criteria': 'customfield_10034',
            'task_created_date': 'created',
            'task_labels': 'labels',
            'sprint': 'customfield_10020',
            'checklist': 'customfield_10035'
        }
        values = []
        for key, value in template.items():
            values.append({
                'host_id': host.id,
                'key': key,
                'value': value,
                'type': 'sdk'
            })

        if not host.template_id:
            host.template_id = self.env['work.base.integration.map.template'].create({})

        values.extend([
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__task_name').id,
                'value': 'summary',
                'host_id': host.id,
                'template_id': host.template_id.id
            },
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__project_id').id,
                'value': 'project',
                'host_id': host.id,
                'template_id': host.template_id.id
            },
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__label_ids').id,
                'value': 'labels',
                'host_id': host.id,
                'template_id': host.template_id.id
            },
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__task_type_id').id,
                'value': 'issuetype',
                'host_id': host.id,
                'template_id': host.template_id.id
            },
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__description').id,
                'value': 'description',
                'host_id': host.id,
                'template_id': host.template_id.id
            },
            {
                'field_id': self.env.ref('work_abc_management.field_work_task__epic_id').id,
                'value': False,
                'host_id': host.id,
                'template_id': host.template_id.id
            }
        ])

        self.create(values)
class HostMapTemplate(models.Model):
    _name = "work.base.integration.map.template"
    _description = "Host Map Template"

    field_ids = fields.One2many("work.field.map", 'template_id', string="Fields")
    