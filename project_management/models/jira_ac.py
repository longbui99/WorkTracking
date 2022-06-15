from datetime import datetime
from odoo import api, fields, models, _


class JiraACs(models.Model):
    _name = "jira.ac"
    _description = "JIRA Acceptance Criteria"
    _order = 'sequence asc, create_date asc'

    sequence = fields.Integer(string="Sequence")
    name = fields.Html(string='Name', required=True, default="")
    display_type = fields.Char(string="Display Type")
    key = fields.Char(string="Key")
    checked = fields.Boolean(string="Checked?")
    is_header = fields.Boolean(string="Header?")
    ticket_id = fields.Many2one("jira.ticket", string="Ticket")
    
    @api.model
    def create(self, values):
        if values.get('is_header', False):
            values['display_type'] = 'line_section'
        return super().create(values)

    def write(self, values):
        if values.get('is_header', False):
            values['display_type'] = 'line_section'
        return super().write(values)

    def update_ac(self, values):
        updated_values = dict()
        if 'checked' in values:
            updated_values['checked'] = values['checked']
        self.write(updated_values)