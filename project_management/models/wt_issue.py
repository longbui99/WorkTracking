import datetime
import json
import pytz
from odoo import api, fields, models, _
from odoo.osv import expression
from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.project_management.utils.time_parsing import convert_second_to_log_format
from Crypto.Cipher import AES
import base64


class JiraProject(models.Model):
    _name = "wt.issue"
    _description = "Task Ticket"
    _order = 'issue_sequence desc, sequence asc, create_date desc'

    pin = fields.Boolean(string='Pin')
    sequence = fields.Integer(string='Sequence')
    issue_name = fields.Char(string='Name', required=True)
    issue_key = fields.Char(string='Ticket Key', required=True)
    issue_url = fields.Char(string='Task Ticket')
    time_log_ids = fields.One2many('wt.time.log', 'issue_id', string='Log Times')
    story_point = fields.Float(string='Estimate')
    story_point_unit = fields.Selection([('general', 'Fibonanci'), ('hrs', 'Hour(s)')], string="Estimate Unit", default="general")
    project_id = fields.Many2one('wt.project', string='Project', required=True)
    assignee_id = fields.Many2one('res.users', string='Assignee')
    tester_id = fields.Many2one("res.users", string="Tester")
    issue_type_id = fields.Many2one("wt.type", string="Type")
    ac_ids = fields.One2many("wt.ac", "issue_id", string="Checklist")
    suitable_assignee = fields.Many2many('res.users', store=False, compute='_compute_suitable_assignee',
                                         compute_sudo=True)
    status_value = fields.Char('Status Raw Value', related='status_id.key')
    status_id = fields.Many2one('wt.status', string='Status')
    duration = fields.Integer('Duration', compute='_compute_duration', store=True)
    progress_cluster_id = fields.Many2one('wt.work.log.cluster', string='Progress Cluster')
    work_log_ids = fields.One2many('wt.work.log', 'issue_id', string='Work Log Statuses')
    active_duration = fields.Integer("Active Duration", compute='_compute_active_duration')
    my_total_duration = fields.Integer("My Total Duration", compute="_compute_my_total_duration")
    last_start = fields.Datetime("Last Start", compute="_compute_last_start")
    issue_sequence = fields.Integer('Ticket Sequence', compute='_compute_issue_sequence', store=True)
    start_date = fields.Datetime("Start Date")
    parent_issue_id = fields.Many2one("wt.issue", string="Parent")
    log_to_parent = fields.Boolean("Log to Parent?")
    children_issue_ids = fields.One2many("wt.issue", "parent_issue_id", store=False)
    duration_in_text = fields.Char(string="Work Logs", compute="_compute_duration_in_text", store=True)
    encode_string = fields.Char(string="Hash String", compute='_compute_encode_string')
    duration_hrs = fields.Float(string="Duration(hrs)", compute="_compute_duration_hrs", store=True)
    sprint_id = fields.Many2one("agile.sprint", string="Sprint")

    @api.depends("duration")
    def _compute_duration_hrs(self):
        for record in self:
            record.duration_hrs = record.duration / 3600

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        if name and operator in ('=', 'ilike', '=ilike', 'like', '=like'):
            args = args or []
            domain = ['|', ('issue_name', operator, name), ('issue_key', operator, name)]
            return self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
        return super(JiraProject, self)._name_search(name=name, args=args, operator=operator, limit=limit,
                                                     name_get_uid=name_get_uid)

    def _compute_last_start(self):
        user_id = self.env.user.id
        for record in self:
            if record.work_log_ids:
                suitable_record = record.work_log_ids.filtered(
                    lambda r: r.user_id.id == user_id and r.state == 'progress')
                if suitable_record:
                    record.last_start = suitable_record.start
                    continue
            record.last_start = False

    def name_get(self):
        # Prefetch the fields used by the `name_get`, so `browse` doesn't fetch other fields
        self.browse(self.ids).read(['issue_key', 'issue_name'])
        return [(template.id, '%s: %s' % (template.issue_key and template.issue_key or '', template.issue_name))
                for template in self]

    @api.depends("duration")
    def _compute_duration_in_text(self):
        for record in self:
            record.duration_in_text = convert_second_to_log_format(record.duration)

    def _compute_my_total_duration(self):
        for record in self:
            record.my_total_duration = sum(
                record.time_log_ids.filtered(lambda r: r.user_id.id == self.env.user.id).mapped('duration'))

    @api.depends('issue_key')
    def _compute_issue_sequence(self):
        for record in self:
            if record.issue_key:
                record.issue_sequence = int(record.issue_key.split('-')[1])

    @api.depends('time_log_ids', 'time_log_ids.duration')
    def _compute_duration(self):
        for record in self:
            record.duration = sum(record.time_log_ids.mapped('duration'))

    def _compute_active_duration(self):
        current_user = self.env.user.id
        now_time = datetime.datetime.now()
        for record in self:
            if record.time_log_ids:
                suitable_time_log_pivot_id = record.time_log_ids.filtered(
                    lambda r: r.user_id.id == current_user and r.state == 'progress')
                if suitable_time_log_pivot_id:
                    cluster_id = suitable_time_log_pivot_id[0].cluster_id.id
                    source = suitable_time_log_pivot_id[0].source
                    log_ids = record.work_log_ids.filtered(lambda r: r.cluster_id.id == cluster_id and
                                                                     r.user_id.id == current_user and
                                                                     r.source == source)
                    data = log_ids.mapped(lambda r: r.duration or (now_time - r.start).total_seconds())
                    record.active_duration = sum(data) + 1
                    continue
            record.active_duration = 0

    def __assign_assignee(self):
        for record in self:
            if record.project_id:
                record.suitable_assignee = record.project_id.allowed_user_ids.ids

    def _compute_suitable_assignee(self):
        self.__assign_assignee()

    @api.onchange('project_id')
    def _onchange_project_id(self):
        self.__assign_assignee()

    def action_pause_work_log(self, values={}):
        source = values.get('source', 'Internal')
        for record in self:
            suitable_time_log_pivot_id = record.time_log_ids.filtered(
                lambda r: r.user_id == self.env.user
                          and r.state == 'progress'
                          and r.source == source
            )
            domain = [
                ('state', '=', 'progress'),
                ('source', '=', source),
                ('user_id', '=', self.env.user.id),
                ('cluster_id', '=', suitable_time_log_pivot_id.cluster_id.id)
            ]
            suitable_time_log = record.work_log_ids.filtered_domain(domain)
            suitable_time_log.write({
                'end': datetime.datetime.now(),
                'state': 'done',
                'description': values.get('description', '')
            })
            record.last_start = False

    def generate_progress_work_log(self, values={}):
        source = values.get('source', 'Internal')
        self.action_pause_work_log(values)
        user_id = self.env.user.id
        for record in self:
            time_log_ids = record.time_log_ids.filtered(
                lambda r: r.user_id.id == user_id and r.state == 'progress' and source == source)
            if not time_log_ids:
                cluster = self.env['wt.work.log.cluster'].create({
                    'name': self.issue_key + "-" + str(len(record.time_log_ids) + 1)
                })
                record.time_log_ids = [fields.Command.create({
                    'description': values.get('description', ''),
                    'cluster_id': cluster.id,
                    'user_id': user_id,
                    'duration': 0,
                    'source': source,
                })]
            else:
                cluster = time_log_ids[0].cluster_id
            record.work_log_ids = [fields.Command.create({
                'start': datetime.datetime.now(),
                'cluster_id': cluster.id,
                'user_id': user_id,
                'source': source,
                'description': values.get('description', '')
            })]
            record.last_start = datetime.datetime.now()
        return self

    def action_done_work(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("project_management.log_work_action_form_view")
        context = json.loads(action['context'])
        context.update({'default_issue_id': self.id})
        action['context'] = context
        return action

    def _get_suitable_log(self):
        record = self
        while record.parent_issue_id and record.log_to_parent:
            record = record.parent_issue_id
        return record

    def action_done_work_log(self, values={}):
        self.action_pause_work_log(values)
        source = values.get('source', 'Internal')
        change_records = self.env['wt.issue']
        for issue in self:
            record = issue._get_suitable_log()
            suitable_time_log_pivot_id = record.time_log_ids.filtered(
                lambda r: r.user_id == self.env.user
                          and r.state == 'progress'
                          and r.source == source
            )
            domain = [
                ('source', '=', source),
                ('user_id', '=', self.env.user.id),
                ('cluster_id', '=', suitable_time_log_pivot_id.cluster_id.id)
            ]
            work_log_ids = record.work_log_ids.filtered_domain(domain)
            if work_log_ids:
                work_log_ids.write({'state': 'done'})
            time_log_id = record.time_log_ids.filtered_domain(domain + [('state', '=', 'progress')])
            total_duration = sum(work_log_ids.mapped('duration'))
            if time_log_id:
                time_log_id.update({
                    'duration': total_duration > 60 and total_duration or 60,
                    'state': 'done',
                    'description': values.get('description', ''),
                })
            record.progress_cluster_id = None
            record.last_start = False
            change_records |= record
        return change_records

    def action_manual_work_log(self, values={}):
        source = values.get('source', 'Internal')
        log_ids = self.env['wt.time.log']
        change_records = self.env['wt.issue']
        start_date = values.get('start_date', False)
        if start_date:
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S%z").astimezone(pytz.utc)
            start_date = start_date.replace(tzinfo=None)
        for issue in self:
            record = issue._get_suitable_log()
            log_ids |= record.env['wt.time.log'].create({
                'description': values.get('description', ''),
                'time': values.get('time', ''),
                'user_id': self.env.user.id,
                'source': source,
                'issue_id': record.id,
                'state': 'done',
                'start_date': start_date
            })
            change_records |= record
            record.last_start = False
        return change_records, log_ids

    def _get_result_management(self):
        return self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)

    @api.model
    def get_all_active(self, values={}):
        employee = self._get_result_management()
        except_ids = self
        source = values.get('source', 'Internal')
        if values.get('except', False):
            except_ids = self.browse(values['except'])
        active_time_ids = self.env['wt.time.log'].search([('user_id', '=', self.env.user.id),
                                                            ('source', '=', source),
                                                            ('state', '=', 'progress')])
        active_issue_ids = (active_time_ids.mapped('issue_id') - except_ids).ids
        self.search([('id', 'in', active_issue_ids)], order=employee.order_style,
                    limit=employee.maximum_relative_result)
        if values.get('limit', False):
            active_issue_ids = active_issue_ids[:values['limit']]
        return active_issue_ids

    def generate_special_search(self, res, employee):
        if 'chain' in res:
            pass

    def get_search_issue_domain(self, res, employee):
        domain = []
        print(res)
        if 'issue' in res:
            domain = expression.AND([domain, [('issue_key', 'ilike', res['issue'])]])
        if 'project' in res:
            project_domain = []
            if res['project'].isupper():
                project_domain = [('project_id.project_key', '=like', res['project']+"%")]
            else:
                project_domain = [('project_id.project_key', 'ilike', res['project'])]
            project_domain = expression.OR([project_domain,[('project_id.project_name', 'ilike', res['project'])]])
            domain = expression.AND([domain, project_domain])
            if 'sprint' in res:
                project_id = self.env["wt.project"].search([('project_key', '=', res['project'])], limit=1)
                if project_id:
                    if 'sprint+' == res['sprint']:
                        sprint_id = project_id.sprint_ids.filtered(lambda r: r.state == 'future')
                    else:
                        sprint_id = project_id.sprint_ids.filtered(lambda r: r.state == 'active')
                    domain = expression.AND([domain, [('sprint_id', 'in', sprint_id.ids)]])
        if 'mine' in res:
            domain = expression.AND([domain, [('assignee_id', '=', employee.user_id.id)]])
        if 'text' in res:
            domain = expression.AND([domain, [('issue_name', 'ilike', res['text'])]])
        if 'name' in res:
            user_ids = self.env['res.users'].with_context(active_test=False).sudo().search(
                ['|', ('login', 'ilike', res['name']), ('partner_id.email', 'ilike', res['name'])])
            domain = expression.AND([domain, ['|', ('assignee_id', 'in', user_ids.ids), ('tester_id', 'in', user_ids.ids)]])
        return domain

    def search_issue_by_criteria(self, payload):
        employee = self._get_result_management()
        res = get_search_request(payload)
        print(json.dumps(res, indent=4))
        domain = self.get_search_issue_domain(res, employee)
        print(json.dumps(domain, indent=4))
        result = self.env["wt.issue"]
        offset = int(self._context.get('offset', 0))
        if len(domain):
            result |= self.search(domain, order=employee.order_style, limit=employee.maximum_search_result, offset=offset)
        return result

    def action_cancel_progress(self, values={}):
        source = values.get('source', 'Internal')
        for record in self:
            time_log = record.time_log_ids.filtered(lambda r: r.user_id == self.env.user and
                                                              r.source == source and r.state == 'progress')
            time_log.unlink()

    def _compute_encode_string(self):
        cipher = AES.new(b'Bui Phi Long LML', AES.MODE_EAX)
        nonce = base64.decodebytes(cipher.nonce)
        one_time_link_env = self.env['one.time.link'].sudo()
        for record in self:
            ciphertext, tag = cipher.encrypt_and_digest(json.dumps({
                "record_id": record.id,
                "uid": record.user_id.id
            }))
            record.encode_string = base64.decodebytes(ciphertext)
            one_time_link_env.create({
                'key': record.encode_string,
                'value': nonce
            })

    def get_acceptance_criteria(self, values={}):
        res = []
        for record in self.ac_ids:
            res.append({
                'id': record.id,
                'content': record.name,
                'is_header': record.is_header,
                'checked': record.checked,
                'sequence': record.sequence
            })
        return res
