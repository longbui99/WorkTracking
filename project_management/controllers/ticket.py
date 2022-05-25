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


class MissingParams(Exception):
    pass


class NotFound(Exception):
    pass


class JiraTicket(http.Controller):

    def _get_ticket(self, ticket_ids):
        if isinstance(ticket_ids, list) or isinstance(ticket_ids, int):
            ticket_ids = request.env['jira.ticket'].browse(ticket_ids)
            if not ticket_ids.exists():
                raise MissingError("Cannot found ticket in our system!")
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
                "url": ticket_id.ticket_url
            })
        return res

    @http.route(['/management/ticket/get/<int:ticket_id>'], type="http", cors="*", methods=['GET'], auth='jwt')
    def get_ticket(self, ticket_id):
        data = self._get_ticket(ticket_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @http.route(['/management/ticket/get-my-all'], type="http", methods=['POST'], auth='jwt')
    def get_all_ticket(self):
        ticket_ids = request.env['jira.ticket'].search([('assignee_id', '=', request.env.user.id)])
        data = self._get_ticket(ticket_ids)
        res = {
            "status": 200,
            "message": "Success",
            "data": data
        }
        return res

    @http.route(['/management/ticket/search/<string:keyword>'], type="http", cors="*", methods=['GET', 'POST'],
                auth='jwt')
    def search_ticket(self, keyword):
        limit = int(request.params.get('limitRecord', 80))
        ticket_ids = request.env['jira.ticket'].with_context(limit=limit).search_ticket_by_criteria(keyword).sorted(lambda r: r.ticket_sequence)
        data = self._get_ticket(ticket_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    def __check_work_log_prerequisite(self):
        id = request.params.get('id')
        key = request.params.get('key')
        if not key and not id:
            raise MissingParams("Ticket's ID or KEY must be specific!")
        ticket_id = request.env['jira.ticket'].search(['|', ('id', '=', id), ('ticket_key', '=', key)])
        if not ticket_id.exists():
            raise NotFound("Cannot found ticket")
        return ticket_id

    @http.route(['/management/ticket/work-log/add'], type="http", cors="*", methods=['GET', 'POST'], auth='jwt')
    def add_ticket_work_log(self):
        try:
            ticket_id = self.__check_work_log_prerequisite()
            ticket_id.generate_progress_work_log(json.loads(request.params.get('payload', "{}")))
            data = self._get_ticket(ticket_id)
        except Exception:
            return http.Response("", content_type='application/json', status=404)
        else:
            return http.Response(json.dumps(data), content_type='application/json', status=200)

    @http.route(['/management/ticket/work-log/pause'], type="http", cors="*", methods=['GET', 'POST'], auth='jwt')
    def pause_ticket_work_log(self):
        try:
            ticket_id = self.__check_work_log_prerequisite()
            ticket_id.action_pause_work_log(json.loads(request.params.get('payload', "{}")))
        except Exception:
            return http.Response("", content_type='application/json', status=404)
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/ticket/work-log/done'], type="http", cors="*", methods=['GET', 'POST'], auth='jwt')
    def done_ticket_work_log(self):
        try:
            ticket_id = self.__check_work_log_prerequisite()
            ticket_id.action_done_work_log(json.loads(request.params.get('payload', "{}")))
        except Exception as e:
            return http.Response(e, content_type='application/json', status=404)
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/ticket/work-log/manual'], type="http", cors="*", methods=['GET', 'POST'],
                auth='jwt')
    def manual_ticket_work_log(self):
        try:
            ticket_id = self.__check_work_log_prerequisite()
            ticket_id.action_manual_work_log(json.loads(request.params.get('payload', "{}")))
        except Exception as e:
            return http.Response(str(e), content_type='application/json', status=404)
        return http.Response("", content_type='application/json', status=200)

    @http.route(['/management/ticket/my-active'], type="http", cors="*", method=["GET", "POST"], auth="jwt")
    def get_related_active(self):
        try:
            active_ticket_ids = request.env['jira.ticket'].get_all_active(
                json.loads(request.params.get("payload", "{}")))
            data = self._get_ticket(active_ticket_ids)
        except Exception as e:
            return http.Response(str(e), content_type='application/json', status=404)
        else:
            return http.Response(json.dumps(data), content_type='application/json', status=200)
