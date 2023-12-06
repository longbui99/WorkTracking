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

class WorkProject(models.Model):
    _inherit = "work.task"

    host_id = fields.Many2one('work.base.integration', string='Work Integration', ondelete="cascade")
    status_value = fields.Char(related='status_id.work_key', store=True, copy=False)
    last_export = fields.Datetime("Last Export Time", copy=False)
    auto_export_success = fields.Boolean(string="Export Successful?", default=True, copy=False)
    sprint_key = fields.Integer(string="Sprint ID on WT", copy=False)
    id_onhost = fields.Integer(string="Task ID", copy=False)
    src_task_id = fields.Many2one("work.task", string="Source Task", copy=False)
    cloned_task_ids = fields.One2many("work.task", 'src_task_id', string="Cloned Tasks", copy=False)

    def export_time_log_to_work(self):
        for record in self:
            record.host_id.export_time_log(record)
            record.last_export = datetime.datetime.now()

    def export_ac_to_work(self):
        for record in self:
            record.host_id.export_acceptance_criteria(record)

    def import_task_work(self):
        self = self.with_context(bypass_cross_user=True)
        res = {'task': self.mapped('task_key')}
        self.host_id.with_context(local_task_domain=[('project_id', '=', self.project_id.id)])._search_load(res)

    def action_done_work_log(self, values={}):
        res = super().action_done_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', self.env.user.id)]).mapped('auto_export_work_log')):
                res.filtered(lambda r: r.host_id.auto_export_work_log).export_time_log_to_work()
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
                if res.host_id.auto_export_work_log:
                    res.host_id.add_time_logs(res, time_log_ids)
                    res.last_export = datetime.datetime.now()
            self.write({'auto_export_success': True})
        except Exception as e:
            _logger.warning(e)
            self.write({'auto_export_success': False})
        return res

    def import_work_logs(self):
        for record in self:
            record.host_id.with_delay().load_work_logs(record)

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
                'content': record.work_raw_name,
                'is_header': record.is_header,
                'checked': record.checked,
                'sequence': record.sequence,
                'need_compile': True
            })
        return res

    def export_task_to_host(self, values={}):
        if values.get('mode', {}).get('worklog', False):
            self.export_time_log_to_work()
        if values.get('mode', {}).get('ac', False):
            self.export_ac_to_work()

    def batch_export(self, pivot_time):
        self.write({'last_export': pivot_time})
        self.export_time_log_to_work()

    def render_batch_update_wizard(self):
        action = self.env.ref("work_base_integration.export_work_log_action_form").read()[0]
        action["context"] = {'default_task_ids': self.ids}
        return action

    def get_search_task_domain(self, res, employee):
        if 'jql' in res:
            return []
        else:
            return super().get_search_task_domain(res, employee)
        
    def export_to_host(self):
        for task in self:
            if task.id_onhost:
                raise UserError("Sorry, we don't support update on JIRA Server yet")
            if not task.host_id:
                if not task.project_id.host_id:
                    raise UserError("Cannot Export to Server")
                else:
                    task.host_id = task.project_id.host_id

        self.env['work.base.integration']._create_tasks(self)

    def clone_to_host(self):
        clone = self.env['clone.to.host'].create({
            'task_ids': [(6, 0, self.ids)]
        })

        action = self.env["ir.actions.actions"]._for_xml_id("work_base_integration.clone_to_host_action_for")
        action['res_id'] = clone.id
        return action
    
    def action_open_cloned_tasks(self):
        action = self.env["ir.actions.actions"]._for_xml_id("work_abc_management.action_work_task")
        action['context'] = {}
        if len(self) == 1:
            action['res_id'] = self.id
            action['view_mode'] = "form"
            action['views'] = False
            action['view_id'] = self.env.ref('work_abc_management.work_task_form_view').id
        elif len(self) > 1:
            action['domain'] = [('id', 'in', self.ids)]
        else:
            raise UserError("Cannot open view because of empty cloned tasks")
        return action

    @api.model
    def map_template_to_values(self, task, values, template, key, template_key):
        if not values.get(key) and task[key].id in template[template_key]:
            values[key] = template[template_key][task[key].id]
        if not values.get(key) and template[template_key].get(False):
            values[key] =  template[template_key][False]
    
    @api.model
    def prepare_value_for_cloned_task(self, task, clone_rule, dest_host, template):
        value = {
            'src_task_id': task.id,
            'host_id': dest_host.id,
            'project_id': clone_rule.project_id.id if clone_rule.project_id else False,
            'epic_id': clone_rule.epic_id.id if clone_rule.epic_id else False,
            'sprint_id': clone_rule.sprint_id.id if clone_rule.sprint_id else False,
            'label_ids': [fields.Command.set(clone_rule.label_ids.ids)],
            'assignee_id': clone_rule.assignee_id.id if clone_rule.assignee_id else False,
            'priority_id': clone_rule.priority_id.id if clone_rule.priority_id else False,
            'task_type_id': clone_rule.task_type_id.id if clone_rule.task_type_id else False,
            'task_name': task.task_name
        }
        if template:
            ir_qweb_env = self.env['ir.qweb']
            for field, (field_html, keep_raw) in template['fields'].items():
                string = ir_qweb_env._render(
                    html.fragment_fromstring(field_html),
                    {'o': task},
                )
                if not keep_raw:
                    string = text_from_html(string)
                value[field.name] = string

            self.map_template_to_values(task, value, template, 'task_type_id', 'types')
            self.map_template_to_values(task, value, template, 'status_id', 'statuses')
            self.map_template_to_values(task, value, template, 'project_id', 'projects')
            self.map_template_to_values(task, value, template, 'epic_id', 'epics')
            self.map_template_to_values(task, value, template, 'priority_id', 'priorities')
            value['task_name'] = (clone_rule.prefix or '') + value['task_name']
        return value

    def action_clone_to_host(self, dest_host, clone_rule):
        task_by_host = defaultdict(lambda: self.env['work.task'])
        for record in self:
            task_by_host[record.host_id] |= record

        hosts = list(task_by_host.keys())
        template_by_host = defaultdict(lambda: dict)

        for host in hosts:
            tmpl = host.load_clone_template(dest_host, clone_rule)
            template_by_host[host] = tmpl
        
        cloned_tasks = self.env['work.task'].search([('host_id', '=', dest_host.id), 
                                                    ('src_task_id', 'in', self.ids)])
        cloned_ids = set(cloned_tasks.mapped('src_task_id').ids)

        values = []
        for host, tasks in task_by_host.items():
            if host != dest_host:
                template = template_by_host[host]
                for task in tasks:
                    if task.id in cloned_ids:
                        continue
                    value = self.prepare_value_for_cloned_task(task, clone_rule, dest_host, template)
                    values.append(value)
                    
        tasks = self.create(values)
        if clone_rule.auto_export:
            tasks.export_to_host()
        return tasks.action_open_cloned_tasks()