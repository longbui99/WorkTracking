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
                ticket_ids |= migrate.sudo().load_by_keys("ticket", [keyword])
            if ticket_ids:
                data = self._get_ticket(ticket_ids)
                return http.Response(json.dumps(data), content_type='application/json', status=200)
        return res
