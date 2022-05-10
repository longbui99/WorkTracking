import requests
import json

from odoo import api, fields, models, _


class JIRAMigration(models.Model):
    _name = 'jira.migration'
    _description = 'JIRA Migration'
    _order = 'sequence asc'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence')
    jira_server_url = fields.Char(string='JIRA Server URL')

    def load_all_project(self):
        self.ensure_one()
        employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        headers = {
            'Authorization': "Bearer " + employee_id.jira_password,
        }
        result = requests.get(f"{self.jira_server_url}/project", headers=headers)
        existing_project = self.env['jira.project'].search([])
        existing_project_dict = {f"{r.project_key}": True for r in existing_project}
        new_project = []
        for record in json.loads(result.text):
            if not existing_project_dict.get(record.get('key', False), False):
                new_project.append({
                    'project_name': record['name'],
                    'project_key': record['key'],
                })

        if new_project:
            self.env['jira.project'].create(new_project)
