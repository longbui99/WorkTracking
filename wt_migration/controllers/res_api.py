import json
from odoo import http, _
from odoo.http import request
from odoo.addons.project_management.controllers.issue import WtIssue
from odoo.addons.project_management.controllers.auth import Auth
from odoo.addons.project_management.utils.error_tracking import handling_req_res
import logging
_logger = logging.getLogger(__name__)

class WtIssueMigration(WtIssue):

    def _get_work_log(self, log): 
        res = super()._get_work_log(log)
        res['exported'] = log.is_exported
        return res

    @handling_req_res
    @http.route(['/management/issue/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt', csrf=False)
    def search_issue(self, keyword, **kwargs):
        try:
            res = super().search_issue(keyword, **kwargs)
            offset = int(kwargs.get('offset', 0))
            if res.data == b'[]' and offset == 0:
                issue_ids = request.env['wt.issue']
                for migrate in request.env['wt.migration'].sudo().search([]):
                    issue_ids |= migrate.sudo().search_issue(keyword)
                if issue_ids:
                    data = self._get_issue(issue_ids)
                    return http.Response(json.dumps(data), content_type='application/json', status=200)
        except Exception as e:
            return http.Response(str(e), content_type='application/json', status=400)
        return res

    @handling_req_res
    @http.route(['/management/issue/fetch/<int:issue_id>'], type="http", cors="*", methods=["GET"],
                auth="jwt", csrf=False)
    def fetch_issue_from_server(self, issue_id, **kwargs):
        if not issue_id:
            return Exception("Need to provide issue id")
        issue_id = request.env['wt.issue'].browse(issue_id)
        res = {'issue': [issue_id.issue_key]}
        issue_id.wt_migration_id._search_load(res)
        data = self._get_issue(issue_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/export'], type="http", cors="*", methods=["POST"], auth="jwt", csrf=False)
    def export_issue_to_server(self, **kwargs):
        request.env['wt.time.log'].browse(kwargs.get('exportIds', [])).force_export()
        return http.Response("", content_type='application/json', status=200)


class AuthInherited(Auth):

    @http.route(['/web/login/jwt'], methods=['GET', 'POST'], cors="*", type="http", auth="none", csrf=False)
    def auth_login_encrypt(self):
        res = super().auth_login_encrypt()
        employee_id = request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1)
        if employee_id and employee_id.auto_remove_access:
            request.env['user.access.code'].sudo().search([('uid', '=', request.env.user.id)],
                                                          order='create_date desc',
                                                          offset=employee_id.maximum_connection).unlink()
        return res
