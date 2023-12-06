import logging
from dateutil.relativedelta import relativedelta
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.osv.expression import AND, OR

_logger = logging.getLogger(__name__)


SPECIAL_KEYS = {'id', 'name', 'key', 'children_nodes', 'rollup_data', 'style'}


def groupby_object(objects, key):
    return_vals = defaultdict(lambda: objects.env[objects._name])
    for record in objects:
        if callable(key):
            to_use_key = key(record)
        else:
            to_use_key = record[key]
        return_vals[to_use_key] |= record
    return return_vals


class AllocationLogNode:
    def __init__(self, parent=None, this=None, records=None, groupby_keys=None, get_col=None, default_values={}):
        self.init_groupby_key = groupby_keys
        self.this = this
        self.records = records or []
        self.parent = parent
        self.get_col = get_col
        self._set_initial_values()
        self._get_default_values(default_vals=default_values)
        if self.groupby_key and self.records:
            groupby_data = groupby_object(self.records, self.groupby_key)
            keys = list(groupby_data.keys())
            if len(keys):
                orm_keys = keys[0].concat(*keys).exists()
                for key in orm_keys.sorted():
                    child_node = self.__class__(self, key, groupby_data[key], self.next_keys, get_col, default_values)
                    self.childrens.append(child_node)

    def _set_initial_values(self):
        self.default_name = False
        self.rollup_data = True
        self.style = "base-line"
        self.childrens = []
        self.lowest_representative = 'duration_hrs'
        self.format = self.get_format()
        self.groupby_key = None
        if self.init_groupby_key:
            self.groupby_key = self.init_groupby_key[0]
            self.next_keys = self.init_groupby_key[1:]

    def get_format(self):
        return "%s"

    def __repr__(self) -> str:
        return self.key
  
    def get(self, key):
        for child in self.childrens:
            if child.key == key:
                return child
        return AllocationLogNode()

    @property
    def children_keys(self):
        return [x.key for x in self.childrens]
    
    @staticmethod
    def _get_key_func(odoo_record):
        return f"{odoo_record._name},{odoo_record.id}" if odoo_record else None

    @property
    def key(self):
        return self._get_key_func(self.this)
    

    @property
    def name(self):
        if self.default_name:
            return self.default_name
        else: 
            return self.format%self.this.display_name if self.this else "NaN"
    
    def set_step_state(self):
        self.vals['rollup_data'] = self.rollup_data 
        self.vals['style'] = self.style
    
    def _get_default_values(self, default_vals={}):
        self.vals = default_vals.copy()
        self.vals['key'] = self.key
        self.vals['name'] = self.name 
        self.vals['children_nodes'] = []
        self.set_step_state()

    def _fetch_record_data(self, record):
        return dict()
    
    def get_records_values(self):
        res = dict()
        for record in self.records:
            vals = self.vals.copy()
            vals['key'] = self._get_key_func(record)
            col = self.get_col(record.start_date)
            if hasattr(record, self.lowest_representative):
                vals[col] = round(record[self.lowest_representative], 2)
            rec_vals = self._fetch_record_data(record)
            if rec_vals:
                for key, value in rec_vals.items():
                    vals[f"{col}_{key}"] = value
            res[vals['key']] = vals
        return res

    @property
    def data(self):
        children_datas = dict()
        for children in self.childrens:
            children_datas.update(children.data)
            self.vals['children_nodes'].append(children.key)
        
        to_process_datas = children_datas
        if not children_datas:
            to_process_datas = self.get_records_values().values()
        else:
            to_process_datas = [children_datas[x] for x in self.vals['children_nodes']]

        for child_data in to_process_datas:
            if child_data.get('rollup_data'):
                for period in self.vals.keys():
                    if period not in SPECIAL_KEYS:
                        self.vals[period] += child_data[period]
        
        self.set_step_state()
        children_datas[self.key] = self.vals
        return children_datas
    
    def merge(self, obj):
        for children in self.childrens:
            is_merged = False
            for obj_children in obj.childrens:
                if children.key == obj_children.key:
                    children | obj_children
                    is_merged = True
                    break
            if not is_merged:
                self.childrens.append(children)

    def __or__(self, obj):
        self.merge(obj)

    
class AllocationResourceNode(AllocationLogNode):
    def __init__(self, parent, this, records, groupby_keys, get_col, default_values={}):
        super().__init__(parent, this, records, groupby_keys, get_col, default_values)

    def _set_initial_values(self):
        res = super()._set_initial_values()
        self.default_name = "Allocation"
        self.lowest_representative = "allocation"
        self.style = "info-line"
        return res
    
    @staticmethod
    def _get_key_func(odoo_record):
        return f"all-{odoo_record._name},{odoo_record.id}" if odoo_record else None
    
    def _fetch_record_data(self, record):
        return {
            'standard_deviation': record.standard_deviation
        }

class WorkAllocationReport(models.Model):
    _name = "work.allocation.report"
    _description = "Work Allocation Report"
    _auto = False

    def get_readable_users(self, user_ids=[]):
        users = self.env['res.users']
        if user_ids:
            users = self.env['res.users'].browse(user_ids).exists()
        else:
            current_employee = self.env.user.employee_id
            launch_domain = [('id', '=', current_employee.id)]
            viewable_employees = self.env['hr.employee'].search(launch_domain)
            users = viewable_employees.mapped('user_id')
        if self._context.get('include_current'):
            users |= self.env.user
        return users
    
    @api.model
    def get_period_label_list(self, start_date, end_date, period_func, **args):
        period_lists = set()
        while start_date < end_date:
            period_lists.add(period_func(start_date))
            start_date += relativedelta(**args)
            
        period_lists.add(period_func(end_date))
        return period_lists
    
    def get_work_logs(self, start_date, end_date, users):
        work_logs = self.sudo().env['work.time.log'].search([('start_date', '>=', start_date), ('start_date', '<', end_date), ('user_id', 'in', users.ids)])
        work_logs.mapped('duration_hrs')
        return work_logs
    
    def get_allocations(self, start_date, end_date, users):
        user_domain = [('user_id', 'in', users.ids)]
        start_date_domain = [('end_date', '>=', start_date), ('start_date', '<=', end_date)]
        end_date_domain = [('start_date', '<=', end_date), ('end_date', '>=', start_date)]
        allocations = self.sudo().env['work.allocation'].search(
            AND([
                user_domain,
                OR([
                    start_date_domain,
                    end_date_domain
                ])
            ])
        )
        allocations.mapped('allocation')
        return allocations
    
    def convert_log_to_resource_key(self, key):
        return "all-" + key
    
    def covert_column_to_style(self, key):
        return "style_" + key

    def compute_column_comparison_style(self, datas, header_values):
        for key, project_log in datas.items():
            if not key or (isinstance(key, str) and not key.startswith("work.project")):
                continue
            allocation_key = self.convert_log_to_resource_key(key)
            if allocation_key in datas:
                project_allocation = datas[allocation_key]
                for item in header_values:
                    key = item['key']
                    standard_deviation = project_allocation.get(f"{key}_standard_deviation") or 0.0
                    if project_allocation[key] > 0:
                        deviation = abs(project_log[key] - project_allocation[key])/project_allocation[key]
                        if deviation > standard_deviation:
                            project_log[self.covert_column_to_style(key)] = "danger"
                        else:
                            project_log[self.covert_column_to_style(key)] = "info"
                    else:
                        project_log[self.covert_column_to_style(key)] = "danger"

    @api.model
    def launch_report(self, expansion_modes=[], group_by='weekly',  user_ids=[], start_date=fields.Datetime.now()-relativedelta(months=1), end_date=fields.Datetime.now(), **kwargs):
        users = self.get_readable_users(user_ids)
        logs = self.get_work_logs(start_date, end_date, users)
        allocations = self.get_allocations(start_date, end_date, users)
        get_col = lambda todo_datetime: f"week_{todo_datetime.isocalendar().week}"
        period_list = self.get_period_label_list(start_date, end_date, get_col, weeks=1)
        values = {weeknum:0.0 for weeknum in period_list}

        groupby_logs_keys = ['user_id', 'project_id'] + expansion_modes
        allocation_logs = AllocationLogNode(None, None, logs, groupby_logs_keys, get_col, values)
        
        groupby_resources_keys = ['user_id', 'project_id']
        values.update({f"{weeknum}_standard_deviation": 0.0 for weeknum in period_list })
        allocation_resources = AllocationResourceNode(None, None, allocations, groupby_resources_keys, get_col, values)

        for user in users:
            key = f"{user._name},{user.id}"
            user_resources = allocation_resources.get(self.convert_log_to_resource_key(key))
            # if user_resources:
            user_logs = allocation_logs.get(key)
            if user_logs:
                projects = user_logs.childrens
                index = 0
                while index < len(projects):
                    project = projects[index]
                    resource_key = self.convert_log_to_resource_key(project.key)
                    if resource_key in user_resources.children_keys:
                        resource_index = user_resources.children_keys.index(resource_key)
                        resource_project = user_resources.childrens[resource_index]
                        resource_project.this = project.this
                        resource_project.rollup_data = False
                        projects.insert(index, resource_project)
                    else:
                        cloned_project = AllocationResourceNode(None, project.this, None, [], get_col, values)
                        cloned_project.rollup_data = False
                        projects.insert(index, cloned_project)
                    index += 2

                for project in user_resources.childrens:
                    if project not in projects:
                        project.rollup_data = False
                        projects.append(project)


        get_headers = lambda todo_datetime: todo_datetime.isocalendar().week
        period_list = self.get_period_label_list(start_date, end_date, get_headers, weeks=1)
        header_values = [{"key": f"week_{weeknum}", "label": f"Week {weeknum}"} for weeknum in period_list]

        datas = allocation_logs.data

        self.compute_column_comparison_style(datas, header_values)
        res = {
            'datas': datas,
            'headers': header_values,
            'initial_nodes': allocation_logs.children_keys,
            'state': ['project_id'],
            'arch': {
                'headerButtons': [
                    {
                        'string': "View Task",
                        'title': 'Task Expansion',
                        'id': '2',
                        'clickParams': {
                            'state': 'project_id',
                            'type': 'object',
                            'kwargs': {
                                'action': 'reload_report',
                                'expansion_modes': ['task_id']
                            }
                        }
                    },
                    # {
                    #     'string': "View Project",
                    #     'title': 'Project Expansion',
                    #     'id': '3',
                    #     'clickParams': {
                    #         'state': 'task_id',
                    #         'type': 'object',
                    #         'kwargs': {
                    #             'action': 'reload_report',
                    #             'expansion_modes': ['project_id']
                    #         }
                    #     }
                    # }
                ],
                'headerVisibleButtons': [
                    {
                        'string': 'Export',
                        'title': "Export",
                        'id': '1',
                        'clickParams': {
                            'state': True,
                            'type': 'object',
                            'action': 'reload_report',
                            'kwargs': []
                        }
                    }
                ]
            }
        }

        
        return res
    
    @api.model
    def action_click_header_button(self, **kwargs):
        if 'reload_report' == kwargs['action']:
            res = self.launch_report(**kwargs)
            if 'expansion_mode' in kwargs:
                res['state'] = kwargs['expansion_mode']
            return res
        else:
            return getattr(self, kwargs['action'])(**kwargs)
        
