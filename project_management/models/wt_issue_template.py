from datetime import datetime
from lxml import html
from lxml import etree
from odoo import api, fields, models, _


def text_from_html(html_fragment):
    """
    Returns the plain non-tag text from an html

    :param html_fragment: document from which text must be extracted

    :return: text extracted from the html
    """
    # lxml requires one single root element
    tree = etree.fromstring('<p>%s</p>' % html_fragment, etree.XMLParser(recover=True))
    return ' '.join(tree.itertext()).replace('\n', '')

class WtIssueTemplate(models.Model):
    _name = "wt.issue.template"
    _description = "Issue Template"
    
    name = fields.Char(string="Name", required=True)
    project_id = fields.Many2one("wt.project", string="Project", required=True, domain=lambda self: [['company_id', 'in', self.env.user.company_ids]])
    company_id = fields.Many2one("res.company", string="Company", related="project_id.company_id")
    epic_id = fields.Many2one("wt.issue", domain="[['epic_ok', '=', True], ['project_id', '=', project_id]]")
    type_id = fields.Many2one("wt.type", string="Type", domain="[['company_id', '=', company_id]]")
    priority_id = fields.Many2one("wt.priority", string="Priority", domain="[['company_id', '=', company_id]]")
    template_line_ids = fields.One2many("wt.issue.template.line", "template_id", string="Template Lines")
    allowed_user_ids = fields.Many2many("res.users", string="Allowed Users")
    cloned_issue_ids = fields.Many2many("wt.issue", string="Cloned Issues")

    def action_clone_template(self):
        issue_env = self.env['wt.issue']
        for record in self:
            values = []
            epic_sequence = record.epic_id.issue_sequence
            for line in record.template_line_ids:
                epic_sequence += 1
                values.append({
                    "issue_name": line.name,
                    "project_id": line.project_id.id,
                    "epic_id": line.epic_id.id,
                    "issue_type_id": line.type_id.id,
                    "priority_id": line.priority_id.id,
                    'issue_sequence': epic_sequence
                })
            record.cloned_issue_ids = [fields.Command.link(issue.id)for issue in issue_env.create(values)]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Clone Issues Successfully'),
            }
        }
    
    @api.onchange('epic_id')
    def _onchange_epic_id(self):
        for line in self.template_line_ids:
            if not line.is_manually_update:
                line.epic_id = self.epic_id

    @api.onchange('type_id')
    def _onchange_type_id(self):
        for line in self.template_line_ids:
            if not line.is_manually_update:
                line.type_id = self.type_id

    @api.onchange('priority_id')
    def _onchange_priority_id(self):
        for line in self.template_line_ids:
            if not line.is_manually_update:
                line.priority_id = self.priority_id

class WtIssueTemplateLine(models.Model):
    _name = "wt.issue.template.line"
    _description = "Issue Template"
    _order = "sequence, id desc"

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string="Summary", compute='_compute_name')
    template = fields.Html(string="Summary Template", required=True, render_engine='qweb', sanitize=False)
    template_id = fields.Many2one("wt.issue.template", string="Template", required=True)
    project_id = fields.Many2one("wt.project", string="Project", related="template_id.project_id")
    epic_id = fields.Many2one("wt.issue", domain="[['epic_ok', '=', True], ['project_id', '=', project_id]]")
    type_id = fields.Many2one("wt.type", string="Type")
    priority_id = fields.Many2one("wt.priority", string="Priority")
    is_manually_update = fields.Boolean(string="Manually Update")

    @api.depends(lambda self: [key for (key, value) in self._fields.items() if value.store])
    def _compute_name(self):
        ir_qweb_env = self.env['ir.qweb']
        for record in self:
            string = False
            if record.template:
                string = text_from_html(ir_qweb_env._render(
                    html.fragment_fromstring(record.template),
                    {'o': record},
                ))
            record.name = string

    @api.model
    def create(self, values):
        res = super().create(values)
        return res
    
    def write(self, values):
        return super().write(values)
    