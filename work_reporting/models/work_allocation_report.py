import json
import types
from typing import Any
from dateutil.relativedelta import relativedelta
from collections import defaultdict

from odoo import models, fields, api, _

import logging

_logger = logging.getLogger(__name__)


# class UserAllocationReport:
#     def __init__(self, user_data, logs, allocations, periodlist, period_func, context={}):
#         self.user_data = user_data
#         self.context = context
#         self.logs = logs
#         self.allocations = allocations
#         self.periodlist = periodlist
#         self.period_func = period_func

#     def get_column_allocations_data(self, allocations):
#         groupby_data = groupby_object(allocations, lambda allocation: self.period_func(allocation.start_date))
#         res = {'name': 'Allocation'}
#         for period in self.periodlist:
#             log_data = groupby_data[period]
#             res[self.get_period_key(period)] = sum(log_data.mapped('allocation'))
#         return res        
    
#     def get_period_key(self, period):
#         return f"period_{period}"
    
#     def get_default_data(self, record):
#         res = {
#             'name': record.display_name,
#             'key': f"{record._name},{record.id}"
#         }
#         for period in self.periodlist:
#             res[self.get_period_key(period)] = 0.0
#         return res

#     def get_column_log_data(self, log):
#         log_period = self.period_func(log.start_date)
#         res = self.get_default_data(log)
#         for period in self.periodlist:
#             if log_period != period:
#                 res[self.get_period_key(period)] = 0
#         return res        
    
#     def get_column_period_data(self, datas):
#         res = {}
#         for period in self.periodlist:
#             key = self.get_period_key(period)
#             res[key] = sum(map(lambda data: data[key], datas))
#         return res        

#     def recursive_get_logs_infos(self, groupby_list, logs, data_list,  higher_key=''):
#         _logger.warning(groupby_list)
#         if not len(groupby_list):
#             res = [ self.get_column_log_data(log) for log in logs]
#             return res
#         groupby_data = groupby_object(logs, groupby_list[0])
#         val_list = []
#         for key, value in groupby_data.items():
#             step_value = {'name': key.display_name, 'key': f"{higher_key},{key._name},{key.id}", 'id': key.id}
#             res_list = self.recursive_get_logs_infos(groupby_list[1:], value, data_list, step_value['key'])
#             step_value.update(self.get_column_period_data(res_list))
#             step_value['children_nodes'] = list(map(lambda r: r['key'], res_list))
#             val_list.append(step_value)
#             data_list.extend(res_list)
#         return val_list

#     def get_groupby_infos(self):
#         groupby_list = ['project_id']
#         if self.context.get('show_task'):
#             groupby_list.append('task_id')
#         if self.context.get('show_log'):
#             groupby_list.append('display_name')
#         return groupby_list

#     @property
#     def data(self):
#         data_list = []
#         groupby_infos = self.get_groupby_infos()
#         project_level_datas = self.recursive_get_logs_infos(groupby_infos, self.logs, data_list, self.user_data['key'])
#         allocations_by_project_id = groupby_object(self.allocations, lambda allocation: allocation.project_id.id)
#         travel_projects = set()
#         for project_data in project_level_datas:
#             travel_projects.add(project_data['id'])
#             allocations = allocations_by_project_id[project_data['id']]
#             allocation_data = self.get_column_allocations_data(allocations)
#             allocation_data['key'] = f"{project_data['key']},allocation"
#             project_data['children_nodes'].append(allocation_data['key'])
#             self.user_data['children_nodes'].append(project_data['key'])

#         for project_id, allocations in allocations_by_project_id.items():
#             if project_id not in travel_projects:
#                 default_data = self.get_default_data(self.env['work.project'].browse(project_id))
#                 project_level_datas.append()
#                 self.user_data['children_nodes'].append(default_data['key'])
#         project_level_datas.extend(data_list)
#         return project_level_datas

SPECIAL_KEYS = {'id', 'name', 'key', 'children_nodes'}
    
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
    def __init__(self, parent, this, records, groupby_keys, get_col, default_values={}):
        self.groupby_key = None
        if groupby_keys:
            self.groupby_key = groupby_keys[0]
            self.next_keys = groupby_keys[1:]
        self.this = this
        self.records = records
        self.parent = parent
        self.childrens = []
        self.get_col = get_col
        if parent and hasattr(parent, 'childrens'):
            self.parent.childrens.append(self)
        self._get_default_values(default_vals=default_values)
        _logger.warning(records)
        if self.groupby_key:
            groupby_data = groupby_object(self.records, self.groupby_key)
            for key, records in groupby_data.items():
                AllocationLogNode(self, key, records, self.next_keys, get_col, default_values)
        
        self.lowest_representative = 'duration_hrs'
    
    @staticmethod
    def _get_key_func(odoo_record):
        return f"{odoo_record._name},{odoo_record.id}" if odoo_record else None

    @property
    def key(self):
        return self._get_key_func(self.this)
    
    def _get_default_values(self, default_vals={}):
        self.vals = default_vals.copy()
        self.vals['key'] = self.key
        self.vals['name'] = self.this.display_name if self.this else "NaN"
        self.vals['children_nodes'] = []
    
    def get_records_values(self):
        res = dict()
        for record in self.records:
            vals = self.vals.copy()
            vals['key'] = self._get_key_func(record)
            vals[self.get_col(record.start_date)] = record[self.lowest_representative]
            res[vals['key']] = vals
        return res

    @property
    def data(self):
        children_datas = dict()
        for children in self.childrens:
            children_datas.update(children.data)
            self.vals['children_nodes'].append(children.key)
        
        if not children_datas:
            return self.get_records_values()

        for child_key, child_data in children_datas.items():
            for period in self.vals.keys():
                if period not in SPECIAL_KEYS:
                    self.vals[period] += child_data[period]
        
        children_datas[self.key] = self.vals
        return children_datas
    
    def __or__(self, obj):
        for children in self.childrens:
            is_merged = False
            for obj_children in obj.childrens:
                if children.key == obj_children.key:
                    children.key | obj_children.key
                    is_merged = True
                    break
            if not is_merged:
                self.childrens.append(children)
            
    
class AllocationResourceNode(AllocationLogNode):
    def __init__(self, parent, this, records, groupby_keys, get_col, default_values={}):
        super().__init__(parent, this, records, groupby_keys, get_col, default_values)
        self.lowest_representative = "allocation"


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
            launch_domain = [('employee_id', 'child_of', current_employee.id)]
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
        allocations = self.sudo().env['work.allocation'].search([('start_date', '>=', start_date), ('end_date', '<=', end_date), ('user_id', 'in', users.ids)])
        allocations.mapped('allocation')
        return allocations

    @api.model
    def launch_allocation_reports(self, group_by='weekly', user_ids=[], start_date=fields.Datetime.now()-relativedelta(months=1), end_date=fields.Datetime.now()):
        users = self.get_readable_users(user_ids)
        logs = self.get_work_logs(start_date, end_date, users)
        allocations = self.get_allocations(start_date, end_date, users)
        get_col = lambda todo_datetime: f"week_{todo_datetime.isocalendar().week}"
        period_list = self.get_period_label_list(start_date, end_date, get_col, weeks=1)
        values = {weeknum:0.0 for weeknum in period_list}

        groupby_logs_keys = ['user_id', 'project_id', 'task_id']
        allocation_logs = AllocationLogNode(None, None, logs, groupby_logs_keys, get_col, values)
        
        groupby_resources_keys = ['user_id', 'project_id']
        allocation_resources = AllocationResourceNode(None, None, allocations, groupby_resources_keys, get_col, values)


        datas = allocation_resources.data

        # logs_by_user = groupby_object(logs, 'user_id')
        # allocations_by_user = groupby_object(allocations, 'user_id')
        # datas = []
        # user_datas = []
        # for user in users:
        #     user_data = {
        #         'name': user.display_name,
        #         'key': f"res.users,{user.id}",
        #         'children_nodes': []
        #     }
        #     user_logs = logs_by_user[user]
        #     user_allocations = allocations_by_user[user]
        #     user_allocation_report = UserAllocationReport(user_data, user_logs, user_allocations, period_list, period_func, self._context)
        #     user_datas.append(user_data)
        #     datas.extend(user_allocation_report.data)
        return json.dumps(datas, indent=4)
