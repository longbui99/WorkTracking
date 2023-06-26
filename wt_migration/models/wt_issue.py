import re
import json
import datetime
import logging
from lxml import html
from lxml import etree
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

def text_from_html(html_fragment):
    """
    Returns the plain non-tag text from an html

    :param html_fragment: document from which text must be extracted

    :return: text extracted from the html
    """
    # lxml requires one single root element
    tree = etree.fromstring('<p>%s</p>' % html_fragment, etree.XMLParser(recover=True))
    return ' '.join(tree.itertext()).replace('\n', '')

class WtProject(models.Model):
    _inherit = "wt.issue"

    wt_migration_id = fields.Many2one('wt.migration', string='Task Migration', ondelete="cascade")
    status_value = fields.Char(related='status_id.wt_key', store=True)
    last_export = fields.Datetime("Last Export Time")
    auto_export_success = fields.Boolean(string="Export Successful?", default=True)
    sprint_key = fields.Integer(string="Sprint ID on WT")
    wt_id = fields.Integer(string="Task ID")
    src_issue_id = fields.Many2one("wt.issue", string="Source Issue")
    cloned_issue_ids = fields.One2many("wt.issue", 'src_issue_id', string="Cloned Issues")

    def export_time_log_to_wt(self):
        for record in self:
            record.wt_migration_id.export_time_log(record)
            record.last_export = datetime.datetime.now()

    def export_ac_to_wt(self):
        for record in self:
            record.wt_migration_id.export_acceptance_criteria(record)

    def import_issue_wt(self):
        res = {'issue': self.mapped('issue_key')}
        self.wt_migration_id._search_load(res)

    def action_done_work_log(self, values={}):
        res = super().action_done_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', self.env.user.id)]).mapped('auto_export_work_log')):
                res.filtered(lambda r: r.wt_migration_id.auto_export_work_log).export_time_log_to_wt()
            res.write({'last_export': datetime.datetime.now()})
            self.write({'auto_export_success': True})
        except Exception as e:
            _logger.warning(e)
            self.write({'auto_export_success': False})
        return res

    def action_manual_work_log(self, values={}):
        self.ensure_one()
        res, time_log_ids = super().action_manual_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', res.env.user.id)]).mapped('auto_export_work_log')):
                if res.wt_migration_id.auto_export_work_log:
                    res.wt_migration_id.add_time_logs(res, time_log_ids)
                    res.last_export = datetime.datetime.now()
            self.write({'auto_export_success': True})
        except Exception as e:
            _logger.warning(e)
            self.write({'auto_export_success': False})
        return res

    def import_work_logs(self):
        for record in self:
            record.wt_migration_id.with_delay().load_work_logs(record)

    @api.model
    def re_export_work_log(self):
        self.search([('auto_export_success', '=', False)]).action_done_work_log({})

    @api.model
    def create(self, values):
        res = super().create(values)
        res.last_export = datetime.datetime.now()
        return res

    def get_acceptance_criteria(self, values={}):
        res = []
        for record in self.ac_ids:
            res.append({
                'id': record.id,
                'content': record.wt_raw_name,
                'is_header': record.is_header,
                'checked': record.checked,
                'sequence': record.sequence,
                'need_compile': True
            })
        return res

    def export_issue_to_server(self, values={}):
        if values.get('mode', {}).get('worklog', False):
            self.export_time_log_to_wt()
        if values.get('mode', {}).get('ac', False):
            self.export_ac_to_wt()

    def batch_export(self, pivot_time):
        self.write({'last_export': pivot_time})
        self.export_time_log_to_wt()

    def render_batch_update_wizard(self):
        action = self.env.ref("wt_migration.export_work_log_action_form").read()[0]
        action["context"] = {'default_issue_ids': self.ids}
        return action

    def get_search_issue_domain(self, res, employee):
        if 'jql' in res:
            return []
        else:
            return super().get_search_issue_domain(res, employee)
        
    def export_to_server(self):
        for issue in self:
            if issue.wt_id:
                raise UserError("Sorry, we don't support update on JIRA Server yet")
            if not issue.wt_migration_id:
                if not issue.project_id.wt_migration_id:
                    raise UserError("Cannot Export to Server")
                else:
                    issue.wt_migration_id = issue.project_id.wt_migration_id

        self.env['wt.migration']._create_issues(self)

    def clone_to_server(self):
        clone = self.env['clone.to.migration'].create({
            'issue_ids': [(6, 0, self.ids)]
        })

        action = self.env["ir.actions.actions"]._for_xml_id("wt_migration.clone_to_migration_action_for")
        action['res_id'] = clone.id
        return action
    
    def action_open_cloned_issues(self):
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.action_wt_issue")
        action['context'] = {}
        if len(self) == 1:
            action['res_id'] = self.id
            action['view_mode'] = "form"
            action['views'] = False
            action['view_id'] = self.env.ref('project_management.wt_issue_form_view').id
        elif len(self) > 1:
            action['domain'] = [('id', 'in', self.ids)]
        else:
            raise UserError("Cannot open view because of empty cloned issues")
        return action

    @api.model
    def map_template_to_values(self, issue, values, template, key, template_key):
        if not values.get(key) and issue[key].id in template[template_key]:
            values[key] = template[template_key][issue[key].id]
        if not values.get(key) and template[template_key].get(False):
            values[key] =  template[template_key][False]
    
    @api.model
    def prepare_value_for_cloned_issue(self, issue, clone_rule, dest_migration, template):
        value = {
            'src_issue_id': issue.id,
            'wt_migration_id': dest_migration.id,
            'project_id': clone_rule.project_id.id if clone_rule.project_id else False,
            'epic_id': clone_rule.epic_id.id if clone_rule.epic_id else False,
            'sprint_id': clone_rule.sprint_id.id if clone_rule.sprint_id else False,
            'label_ids': [fields.Command.set(clone_rule.label_ids.ids)],
            'assignee_id': clone_rule.assignee_id.id if clone_rule.assignee_id else False,
            'priority_id': clone_rule.priority_id.id if clone_rule.priority_id else False,
            'issue_type_id': clone_rule.issue_type_id.id if clone_rule.issue_type_id else False,
            'issue_name': issue.issue_name
        }
        if template:
            ir_qweb_env = self.env['ir.qweb']
            for field, (field_html, keep_raw) in template['fields'].items():
                string = ir_qweb_env._render(
                    html.fragment_fromstring(field_html),
                    {'o': issue},
                )
                if not keep_raw:
                    string = text_from_html(string)
                value[field.name] = string

            self.map_template_to_values(issue, value, template, 'issue_type_id', 'types')
            self.map_template_to_values(issue, value, template, 'status_id', 'statuses')
            self.map_template_to_values(issue, value, template, 'project_id', 'projects')
            self.map_template_to_values(issue, value, template, 'epic_id', 'epics')
            self.map_template_to_values(issue, value, template, 'priority_id', 'priorities')
        return value

    def action_clone_to_server(self, dest_migration, clone_rule):
        issue_by_migration = defaultdict(lambda: self.env['wt.issue'])
        for record in self:
            issue_by_migration[record.wt_migration_id] |= record

        migrations = list(issue_by_migration.keys())
        template_by_migration = defaultdict(lambda: dict)

        for migration in migrations:
            tmpl = migration.load_clone_template(dest_migration, clone_rule)
            template_by_migration[migration] = tmpl
        
        cloned_issues = self.env['wt.issue'].search([('wt_migration_id', '=', dest_migration.id), 
                                                    ('src_issue_id', 'in', self.ids)])
        cloned_ids = set(cloned_issues.mapped('src_issue_id').ids)

        values = []
        for migration, issues in issue_by_migration.items():
            if migration != dest_migration:
                template = template_by_migration[migration]
                for issue in issues:
                    if issue.id in cloned_ids:
                        continue
                    value = self.prepare_value_for_cloned_issue(issue, clone_rule, dest_migration, template)
                    values.append(value)
                    
        issues = self.create(values)
        if clone_rule.auto_export:
            issues.export_to_server()
        return issues.action_open_cloned_issues()