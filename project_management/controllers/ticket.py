# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import http, _
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


class JiraTicket(http.Controller):

    def _get_ticket(self, ticket_ids):
        if ticket_ids and isinstance(ticket_ids, list) or isinstance(ticket_ids, int):
            ticket_ids = request.env['jira.ticket'].browse(ticket_ids)
            if not ticket_ids.exists():
                return MissingError("Cannot found ticket in our system!")
        res = []
        for ticket_id in ticket_ids:
            res.append({
                "id": ticket_id.id,
                "name": ticket_id.ticket_name,
                "key": ticket_id.ticket_key,
                "point": ticket_id.story_point,
                "project": ticket_id.project_id.project_name,
                "projectKey": ticket_id.project_id.project_key,
                "assignee": ticket_id.assignee_id.partner_id.name,
                "assigneeEmail": ticket_id.assignee_id.partner_id.email,
                "status": ticket_id.status_id.name,
                "total_duration": ticket_id.duration,
                "my_total_duration": ticket_id.my_total_duration,
                "active_duration": ticket_id.active_duration,
                "last_start": ticket_id.last_start and ticket_id.last_start.isoformat() or False,
                "url": ticket_id.ticket_url,
                'type_url': ticket_id.ticket_type_id.img_url,
                'type_name': ticket_id.ticket_type_id.name,
                'sprint': ticket_id.sprint_id.name
            })
        return res

    @handling_req_res
    @http.route(['/management/ticket/get/<int:ticket_id>'], type="http", cors="*", methods=['GET'], csrf=False, auth='jwt')
    def get_ticket(self, ticket_id, **kwargs):
        data = self._get_ticket(ticket_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/get-my-all'], type="http", methods=['GET'], csrf=False, auth='jwt')
    def get_all_ticket(self, **kwargs):
        ticket_ids = request.env['jira.ticket'].search([('assignee_id', '=', request.env.user.id)])
        data = self._get_ticket(ticket_ids)
        res = {
            "status": 200,
            "message": "Success",
            "data": data
        }
        return res

    @handling_req_res
    @http.route(['/management/ticket/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt')
    def search_ticket(self, keyword, **kwargs):
        limit = int(request.params.get('limitRecord', 80))
        ticket_ids = request.env['jira.ticket'].with_context(limit=limit).search_ticket_by_criteria(keyword)
        data = self._get_ticket(ticket_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    def check_work_log_prerequisite(self, **kwargs):
        id = request.params.get('id')
        key = request.params.get('key')
        if not key and not id:
            raise MissingParams("Ticket's ID or KEY must be specific!")
        ticket_id = request.env['jira.ticket'].search(['|', ('id', '=', id), ('ticket_key', '=', key)])
        if not ticket_id.exists():
            raise NotFound("Cannot found ticket")
        return ticket_id

    @handling_req_res
    @http.route(['/management/ticket/work-log/add'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def add_ticket_work_log(self, **kwargs):
        ticket_id = self.check_work_log_prerequisite()
        ticket_id.generate_progress_work_log(request.params.get('payload', {}))
        data = self._get_ticket(ticket_id)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/work-log/pause'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def pause_ticket_work_log(self, **kwargs):
        ticket_id = self.check_work_log_prerequisite()
        ticket_id.action_pause_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/work-log/done'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def done_ticket_work_log(self, **kwargs):
        request.params = json.loads(request.httprequest.data)
        ticket_id = self.check_work_log_prerequisite()
        ticket_id.action_done_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/ticket/work-log/manual'], type="http", cors="*", methods=['POST'], csrf=False, auth='jwt')
    def manual_ticket_work_log(self, **kwargs):
        request.params = json.loads(request.httprequest.data)
        ticket_id = self.check_work_log_prerequisite()
        ticket_id.action_manual_work_log(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/work-log/cancel'], type="http", cors="*", methods=['POST'], csrf=False,
                auth='jwt')
    def cancel_ticket_work_log(self, **kwargs):
        ticket_id = self.check_work_log_prerequisite()
        ticket_id.action_cancel_progress(request.params.get('payload', {}))
        return http.Response("", content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/my-active'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_related_active(self, **kwargs):
        active_ticket_ids = request.env['jira.ticket'].get_all_active(json.loads(request.params.get("payload", '{}')))
        data = self._get_ticket(active_ticket_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/ticket/favorite'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_favorite_tickets(self, **kwargs):
        ticket_ids = request.env["hr.employee"].search([('user_id', '=', request.env.user.id)], limit=1).favorite_ticket_ids
        data = self._get_ticket(ticket_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    def __check_ac_prequisite(self, **kwargs):
        id = request.params.get('id')
        if not isinstance(id, int):
            raise MissingParams("Ticket's ID must be specific!")
        ac_id = request.env['jira.ac'].browse(int(id))
        return ac_id

    @handling_req_res
    @http.route(['/management/ticket/ac'], type="http", cors="*", methods=["GET"], csrf=False, auth="jwt")
    def get_acceptance_criteria(self, **kwargs):
        ticket_id = self.check_work_log_prerequisite()
        data = ticket_id.get_acceptance_criteria(request.params.get('payload', {}))
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
        request.env['jira.ac'].browse(request.params.get('acID', 0), ).unlink()
        data = {'status': 'ok'}
        return http.Response(json.dumps(data), content_type='application/json', status=200)