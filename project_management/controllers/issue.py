# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import http, fields, _
from odoo.http import request
from odoo.osv import expression
from odoo.tools import consteq, plaintext2html
from odoo.addons.mail.controllers import mail
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.addons.project_management.utils.search_parser import get_search_request
from odoo.addons.project_management.utils.error_tracking import handling_req_res


class MissingParams(Exception):
    pass


class NotFound(Exception):
    pass


class WtIssue(http.Controller):

    def _get_issue(self, issue_ids):
        if issue_ids and isinstance(issue_ids, list) or isinstance(issue_ids, int):
            issue_ids = request.env['wt.issue'].browse(issue_ids)
            if not issue_ids.exists():
                return str(MissingError("Cannot found issue in our system!"))
        res = []
        for issue_id in issue_ids:
            res.append({
                "id": issue_id.id,
                "name": issue_id.issue_name,
                "key": issue_id.issue_key,
                "point": issue_id.story_point,
                "estimate_unit": issue_id.story_point_unit,
                "project": issue_id.project_id.project_name,
                "projectKey": issue_id.project_id.project_key,
                "assignee": issue_id.assignee_id.partner_id.name,
                "assigneeEmail": issue_id.assignee_id.partner_id.email,
                "tester": issue_id.tester_id.partner_id.name,
                "status": issue_id.status_id.name,
                "status_key": issue_id.status_id.wt_key,
                "total_duration": issue_id.duration,
                "my_total_duration": issue_id.my_total_duration,
                "active_duration": issue_id.active_duration,
                "last_start": issue_id.last_start and issue_id.last_start.isoformat() or False,
                "url": issue_id.issue_url,
                'type_url': issue_id.issue_type_id.img_url,
                'type_name': issue_id.issue_type_id.name,
                'sprint': issue_id.sprint_id.name
            })
        return res

    @handling_req_res
    @http.route(['/management/issue/get/<int:issue_id>'], type="http", cors="*", methods=['GET'], csrf=False, auth='jwt')
    def get_issue(self, issue_id, **kwargs):
        data = self._get_issue(issue_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/get-my-all'], type="http", methods=['GET'], csrf=False, auth='jwt')
    def get_all_issue(self, **kwargs):
        issue_ids = request.env['wt.issue'].search([('assignee_id', '=', request.env.user.id)])
        data = self._get_issue(issue_ids)
        res = {
            "status": 200,
            "message": "Success",
            "data": data
        }
        return res

    @handling_req_res
    @http.route(['/management/issue/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt')
    def search_issue(self, keyword, **kwargs):
        offset = int(kwargs.get('offset', 0))
        issue_ids = request.env['wt.issue'].with_context(offset=offset).search_issue_by_criteria(keyword)
        data = self._get_issue(issue_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)
    
    @handling_req_res
    @http.route(['/management/issue/my-active'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_related_active(self, **kwargs):
        active_issue_ids = request.env['wt.issue'].get_all_active(json.loads(request.params.get("payload", '{}')))
        data = self._get_issue(active_issue_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    # @handling_req_res
    @http.route(['/management/issue/favorite'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_favorite_issues(self, **kwargs):
        issue_ids = request.env["hr.employee"].search([('user_id', '=', request.env.user.id)], limit=1).favorite_issue_ids
        data = self._get_issue(issue_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/favorite/add'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def add_favorite_issue(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        employee_id = request.env["hr.employee"].search([('user_id', '=', request.env.user.id)], limit=1)
        employee_id.favorite_issue_ids = [fields.Command.link(issue_id.id)]
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/favorite/delete'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def remove_favorite_issue(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        employee_id = request.env["hr.employee"].search([('user_id', '=', request.env.user.id)], limit=1)
        employee_id.favorite_issue_ids = [fields.Command.unlink(issue_id.id)]
        return http.Response("", content_type='application/json', status=200)

    def check_work_log_prerequisite(self, **kwargs):
        id = request.params.get('id')
        key = request.params.get('key')
        if not key and not id:
            raise MissingParams("Issue's ID or KEY must be specific!")
        issue_id = request.env['wt.issue'].search(['|', ('id', '=', id), ('issue_key', '=', key)])
        if not issue_id.exists():
            raise NotFound("Cannot found issue")
        return issue_id

    @handling_req_res
    @http.route(['/management/issue/work-log/add'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def add_issue_work_log(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        issue_id.generate_progress_work_log(request.params.get('payload', {}))
        data = self._get_issue(issue_id)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/pause'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def pause_issue_work_log(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        issue_id.action_pause_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/done'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def done_issue_work_log(self, **kwargs):
        request.params = json.loads(request.httprequest.data)
        issue_id = self.check_work_log_prerequisite()
        issue_id.action_done_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/issue/work-log/manual'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def manual_issue_work_log(self, **kwargs):
        request.params = json.loads(request.httprequest.data)
        issue_id = self.check_work_log_prerequisite()
        issue_id.action_manual_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/cancel'], type="http", cors="*", methods=['POST'], csrf=False,
                auth='jwt')
    def cancel_issue_work_log(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        issue_id.action_cancel_progress(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    def _get_work_log(self, log): 
        return {
                "id": log.id,
                "key": log.issue_id.issue_key,
                "duration": log.duration,
                "project": log.project_id.id,
                "issue": log.issue_id.id,
                "issueName": log.issue_id.issue_name,
                "description": log.description,
                "start_date": log.start_date.isoformat(),
                'type_url': log.issue_id.issue_type_id.img_url
            }
    
    def _get_work_logs(self, log_ids):
        if log_ids and isinstance(log_ids, list) or isinstance(log_ids, int):
            log_ids = request.env['wt.time.log'].browse(log_ids)
            if not log_ids.exists():
                return str(MissingError("Cannot found log in our system!"))
        res = []
        for log in log_ids:
            res.append(self._get_work_log(log))
        return res
    
    @handling_req_res
    @http.route(['/management/issue/work-log/history'], type="http", cors="*", methods=['GET'], auth='jwt')
    def get_history_work_logs(self, **kwargs):
        log_ids = request.env['wt.time.log'].with_context(kwargs).load_history()
        data = self._get_work_logs(log_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    def __check_ac_prequisite(self, **kwargs):
        id = request.params.get('id')
        if not isinstance(id, int):
            raise MissingParams("Issue's ID must be specific!")
        ac_id = request.env['wt.ac'].browse(int(id))
        return ac_id
    
    @http.route(['/management/issue/work-log/update'], type="http", cors="*", methods=['POST'], auth='jwt', csrf=False)
    def update_done_work_logs(self, **kwargs):
        params = json.loads(request.httprequest.data)
        time_id = params.pop('id')
        params.pop('jwt')
        request.env['wt.time.log'].browse(time_id).write(params)
        data = self._get_work_logs(time_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)
    
    @handling_req_res
    @http.route(['/management/issue/work-log/delete/<int:log_id>'], type="http", cors="*", methods=['POST'], auth='jwt', csrf=False)
    def delete_done_work_logs(self, log_id, **kwargs):
        request.env['wt.time.log'].browse(log_id).unlink()
        return http.Response("", content_type='application/json', status=200)

    def __check_ac_prequisite(self, **kwargs):
        id = request.params.get('id')
        if not isinstance(id, int):
            raise MissingParams("Issue's ID must be specific!")
        ac_id = request.env['wt.ac'].browse(int(id))
        return ac_id

    @handling_req_res
    @http.route(['/management/issue/ac'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_acceptance_criteria(self, **kwargs):
        issue_id = self.check_work_log_prerequisite()
        data = issue_id.get_acceptance_criteria(request.params.get('payload', {}))
        return http.Response(json.dumps(data), content_type='application/json', status=200)
        
    @handling_req_res
    @http.route(['/management/ac'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def update_acceptance_criteria(self, **kwargs):
        ac_id = self.__check_ac_prequisite()
        id_ac = ac_id.update_ac(request.params.get('payload', {}))
        return http.Response(json.dumps(id_ac), content_type='application/json', status=200)
        
    @handling_req_res
    @http.route(['/management/ac/delete'], type="http", cors="*", methods=["POST"], csrf=False, auth="jwt")
    def delete_acceptance_criteria(self, **kwargs):
        request.env['wt.ac'].browse(request.params.get('acID', 0), ).unlink()
        data = {'status': 'ok'}
        return http.Response(json.dumps(data), content_type='application/json', status=200)