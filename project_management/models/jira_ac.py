from datetime import datetime
from odoo import api, fields, models, _


class JiraACs(models.Model):
    _name = "jira.ac"
    _description = "JIRA Acceptance Criteria"
    _order = 'sequence, float_sequence, id'

    sequence = fields.Integer(string="Sequence")
    float_sequence = fields.Float(string="Float Sequence")
    name = fields.Html(string='Name', required=True, default="")
    display_type = fields.Char(string="Display Type")
    key = fields.Char(string="Key")
    checked = fields.Boolean(string="Checked?")
    is_header = fields.Boolean(string="Header?")
    ticket_id = fields.Many2one("jira.ticket", string="Ticket")

    @api.model
    def create(self, values):
        if 'is_header' in values:
            if values['is_header']:
                values['display_type'] = 'line_section'
            else:
                values['display_type'] = ''
        return super().create(values)

    def write(self, values):
        if 'is_header' in values:
            if values['is_header']:
                values['display_type'] = 'line_section'
            else:
                values['display_type'] = ''
        return super().write(values)

    def update_ac(self, values):
        if self.exists():
            self.write(values)
            return self.id
        else:
            res = self.create(values)
            return res.id
