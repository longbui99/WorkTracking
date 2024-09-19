# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import traceback

from odoo import http, fields, _
from odoo.http import request
from odoo.osv import expression
from odoo.tools import consteq, plaintext2html
from odoo.addons.mail.controllers import mail
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.addons.work_abc_management.utils.search_parser import get_search_request
from odoo.addons.work_abc_management.utils.error_tracking import handling_req_res



import logging

_logger = logging.getLogger(__name__)


class MissingParams(Exception):
    pass


class NotFound(Exception):
    pass


class WorkTask(http.Controller):

    def _get_task_data(self, task_id):
        return {
            "id": task_id.id,
            "name": task_id.task_name,
            "key": task_id.task_key,
            "point": task_id.story_point,
            "estimate_unit": task_id.story_point_unit,
            "project": task_id.project_id.project_name,
            "projectKey": task_id.project_id.project_key,
            "assignee": task_id.assignee_id.partner_id.name,
            "assigneeEmail": task_id.assignee_id.partner_id.email,
            "tester": task_id.tester_id.partner_id.name,
            "status": task_id.status_id.name,
            "status_key": task_id.status_id.work_key,
            "total_duration": task_id.duration,
            "my_total_duration": task_id.my_total_duration,
            "active_duration": task_id.active_duration,
            "last_start": task_id.last_start and task_id.last_start.isoformat() or False,
            "url": task_id.task_url,
            'type_url': task_id.task_type_id.img_url,
            'type_name': task_id.task_type_id.name,
            'sprint': task_id.sprint_id.name,
            'applicable_date': task_id.applicable_date.isoformat(),
        }
    
    def _get_tasks_data(self, tasks):
        res = []
        for task in tasks:
            res.append(self._get_task_data(task))
        return res
    
    def _get_task(self, task_ids):
        if task_ids and isinstance(task_ids, list) or isinstance(task_ids, int):
            task_ids = request.env['work.task'].browse(task_ids)
            if not task_ids.exists():
                return str(MissingError("Cannot found task in our system!"))
        res = self._get_tasks_data(task_ids)
        return res

    @handling_req_res
    @http.route(['/management/task/get/<int:task_id>',
                 '/management/issue/get/<int:task_id>'], type="http", cors="*", methods=['GET'], csrf=False, auth='jwt')
    def get_task(self, task_id, **kwargs):
        data = self._get_task(task_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/get-my-all',
                 '/management/issue/get-my-all'], type="http", methods=['GET'], csrf=False, auth='jwt')
    def get_all_task(self, **kwargs):
        task_ids = request.env['work.task'].search([('assignee_id', '=', request.env.user.id)])
        data = self._get_task(task_ids)
        res = {
            "status": 200,
            "message": "Success",
            "data": data
        }
        return res

    @handling_req_res
    @http.route(['/management/task/search/<string:keyword>',
                 '/management/issue/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt')
    def search_task(self, keyword, **kwargs):
        offset = int(kwargs.get('offset', 0))
        task_ids = request.env['work.task'].with_context(offset=offset).search_task_by_criteria(keyword)
        data = self._get_task(task_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)
    
    @handling_req_res
    @http.route(['/management/task/search',
                 '/management/issue/search'], type="http", cors="*", methods=['POST'],auth='jwt')
    def search_task_post(self):
        kwargs = request.share_params
        offset = int(kwargs.get('offset', 0))
        keyword = kwargs.get('query', '')
        task_ids = request.env['work.task'].with_context(offset=offset).search_task_by_criteria(keyword)
        data = self._get_task(task_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)
    
    @handling_req_res
    @http.route(['/management/task/my-active',
                 '/management/issue/my-active'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_related_active(self, **kwargs):
        active_task_ids = request.env['work.task'].get_all_active(json.loads(request.share_params.get("payload", '{}')))
        data = self._get_task(active_task_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    # @handling_req_res
    @http.route(['/management/task/favorite',
                 '/management/issue/favorite'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_favorite_tasks(self, **kwargs):
        task_ids = request.env.user.employee_id.favorite_task_ids
        data = self._get_task(task_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/favorite/add',
                 '/management/issue/favorite/add'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def add_favorite_task(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        request.env.user.employee_id.favorite_task_ids = [fields.Command.link(task_id.id)]
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/favorite/delete',
                 '/management/issue/favorite/delete'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def remove_favorite_task(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        request.env.user.employee_id.favorite_task_ids = [fields.Command.unlink(task_id.id)]
        return http.Response("", content_type='application/json', status=200)

    def check_work_log_prerequisite(self, **kwargs):
        id = request.share_params.get('id')
        key = request.share_params.get('key')
        if not key and not id:
            raise MissingParams("Task's ID or KEY must be specific!")
        task_id = request.env['work.task'].search(['&', ('task_key', '!=', False), '|', ('id', '=', id), ('task_key', '=', key)])
        if not task_id.exists():
            raise NotFound("Cannot found task")
        return task_id

    @handling_req_res
    @http.route(['/management/task/work-log/add',
                 '/management/issue/work-log/add'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def add_task_work_log(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        task_id.generate_progress_work_log(request.share_params.get('payload', {}))
        data = self._get_task(task_id)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/work-log/pause',
                 '/management/issue/work-log/pause'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def pause_task_work_log(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        task_id.action_pause_work_log(request.share_params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/work-log/done',
                 '/management/issue/work-log/done'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def done_task_work_log(self, **kwargs):
        request.share_params = json.loads(request.httprequest.data)
        task_id = self.check_work_log_prerequisite()
        task_id.action_done_work_log(request.share_params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/task/work-log/manual',
                 '/management/issue/work-log/manual'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def manual_task_work_log(self, **kwargs):
        request.share_params = json.loads(request.httprequest.data)
        task_id = self.check_work_log_prerequisite()
        task_id.action_manual_work_log(request.share_params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/work-log/cancel',
                 '/management/issue/work-log/cancel'], type="http", cors="*", methods=['POST'], csrf=False,
                auth='jwt')
    def cancel_task_work_log(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        task_id.action_cancel_progress(request.share_params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    def _get_work_log(self, log): 
        return {
                "id": log.id,
                "key": log.task_id.task_key,
                "duration": log.duration,
                "project": log.project_id.id,
                "projectName": log.project_id.project_name,
                "task": log.task_id.id,
                "taskName": log.task_id.task_name,
                'issue': log.task_id.id,
                'issueName': log.task_id.task_name,
                "description": log.description,
                "start_date": log.start_date.isoformat(),
                'type_url': log.task_id.task_type_id.img_url
            }
    
    def _get_work_logs(self, log_ids):
        if log_ids and isinstance(log_ids, list) or isinstance(log_ids, int):
            log_ids = request.env['work.time.log'].browse(log_ids)
            if not log_ids.exists():
                return str(MissingError("Cannot found log in our system!"))
        res = []
        for log in log_ids:
            res.append(self._get_work_log(log))
        return res
    
    @handling_req_res
    @http.route(['/management/task/work-log/history',
                 '/management/issue/work-log/history'], type="http", cors="*", methods=['GET'], auth='jwt')
    def get_history_work_logs(self, **kwargs):
        log_ids = request.env['work.time.log'].with_context(kwargs).load_history()
        data = self._get_work_logs(log_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    def __check_ac_prequisite(self, **kwargs):
        id = request.share_params.get('id')
        if not isinstance(id, int):
            raise MissingParams("Task's ID must be specific!")
        ac_id = request.env['work.ac'].browse(int(id))
        return ac_id
    
    @http.route(['/management/task/work-log/update',
                 '/management/issue/work-log/update'], type="http", cors="*", methods=['POST'], auth='jwt', csrf=False)
    def update_done_work_logs(self, **kwargs):
        params = json.loads(request.httprequest.data)
        time_id = params.pop('id')
        params.pop('jwt')
        request.env['work.time.log'].browse(time_id).write(params)
        data = self._get_work_logs(time_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)
    
    @handling_req_res
    @http.route(['/management/task/work-log/delete/<int:log_id>',
                 '/management/issue/work-log/delete/<int:log_id>'], type="http", cors="*", methods=['POST'], auth='jwt', csrf=False)
    def delete_done_work_logs(self, log_id, **kwargs):
        request.env['work.time.log'].browse(log_id).unlink()
        return http.Response("", content_type='application/json', status=200)

    def __check_ac_prequisite(self, **kwargs):
        id = request.share_params.get('id')
        if not isinstance(id, int):
            raise MissingParams("Task's ID must be specific!")
        ac_id = request.env['work.ac'].browse(int(id))
        return ac_id

    @handling_req_res
    @http.route(['/management/task/ac',
                 '/management/issue/ac'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_acceptance_criteria(self, **kwargs):
        task_id = self.check_work_log_prerequisite()
        data = task_id.get_acceptance_criteria(request.share_params.get('payload', {}))
        return http.Response(json.dumps(data), content_type='application/json', status=200)
        
    @handling_req_res
    @http.route(['/management/ac'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def update_acceptance_criteria(self, **kwargs):
        ac_id = self.__check_ac_prequisite()
        id_ac = ac_id.update_ac(request.share_params.get('payload', {}))
        return http.Response(json.dumps(id_ac), content_type='application/json', status=200)
        
    @handling_req_res
    @http.route(['/management/ac/delete'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def delete_acceptance_criteria(self, **kwargs):
        request.env['work.ac'].browse(request.share_params.get('acID', 0), ).unlink()
        data = {'status': 'ok'}
        return http.Response(json.dumps(data), content_type='application/json', status=200)