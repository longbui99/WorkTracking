import json
from odoo import http, _
from odoo.http import request
from odoo.addons.project_management.controllers.ticket import JiraTicket


class JiraTicketMigration(JiraTicket):

    @http.route(['/management/ticket/search/<string:keyword>'], type="http", cors="*", methods=['GET', 'POST'],
                auth='jwt')
    def search_ticket(self, keyword):
        res = super().search_ticket(keyword)
        if res.data == b'[]':
            ticket_ids = request.env['jira.ticket']
            for migrate in request.env['jira.migration'].sudo().search([]):
                ticket_ids |= migrate.sudo().search_ticket(keyword)
            if ticket_ids:
                data = self._get_ticket(ticket_ids)
                return http.Response(json.dumps(data), content_type='application/json', status=200)
        return res

    @http.route(['/management/ticket/fetch/<int:ticket_id>'], type="http", cors="*", method=["GET", "POST"], auth="jwt")
    def fetch_ticket_from_server(self, ticket_id):
        try:
            if not ticket_id:
                raise Exception("Need to provide ticket id")
            ticket_id = request.env['jira.ticket'].browse(ticket_id)
            ticket_id.jira_migration_id.search_load('ticket', [ticket_id.ticket_key])
        except Exception as e:
            return http.Response(str(e), content_type='application/json', status=404)
        else:
            return http.Response("", content_type='application/json', status=200)
