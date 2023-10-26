import json
from odoo import http, _
from odoo.http import request
from odoo.addons.project_management.controllers.issue import WtIssue
from odoo.addons.project_management.controllers.auth import Auth
from odoo.addons.project_management.utils.error_tracking import handling_req_res
from odoo.addons.web.controllers.main import Binary
import logging
_logger = logging.getLogger(__name__)

class WtIssueMigration(WtIssue):

    def _fill_default_type_url(self, records):
        default_type_url = False
        for record in records:
            if not record['type_url']:
                if not default_type_url:
                    default_type_url = request.env['ir.config_parameter'].sudo().get_param('default.type.url')
                record['type_url'] = default_type_url
        return records

    def _get_work_log(self, log): 
        log.mapped('issue_id.wt_migration_id.host_image_url')
        res = super()._get_work_log(log)
        res['exported'] = log.export_state
        res['host_image_url'] = log.issue_id.wt_migration_id.host_image_url
        return res

    def _get_work_logs(self, log_ids):
        res = super()._get_work_logs(log_ids)
        return self._fill_default_type_url(res)
    
    def _get_issue_data(self, issue):
        res = super()._get_issue_data(issue)
        res['host_image_url'] = issue.wt_migration_id.host_image_url
        return res

    def _get_issues_data(self, issues):
        res = super()._get_issues_data(issues)
        return self._fill_default_type_url(res)

    @handling_req_res
    @http.route(['/management/issue/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt', csrf=False)
    def search_issue(self, keyword, **kwargs):
        try:
            res = super().search_issue(keyword, **kwargs)
            offset = int(kwargs.get('offset', 0))
            if res.data == b'[]' and offset == 0:
                issue_ids |= request.env['wt.migration'].query_candidate_issue()
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
        issue_id.import_issue_wt()
        data = self._get_issue(issue_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/export'], type="http", cors="*", methods=["POST"], auth="jwt", csrf=False)
    def export_issue_to_server(self, **kwargs):
        time_ids = request.env['wt.time.log'].browse(kwargs.get('exportIds', [])).exists().force_export()
        data = self._get_work_logs(time_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/issue/work-log/compare'], type="http", cors="*", methods=["POST"], auth="jwt", csrf=False)
    def compare_log_to_server(self, **kwargs):
        data = request.env['wt.time.log'].browse(kwargs.get('ids', [])).compare_with_external()
        return http.Response(json.dumps(data), content_type='application/json', status=200)


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


class Content:

    @http.route(['/public_image/<int:id>',], type='http', auth="none")
    def content_image(self, *args, **kwargs):
        # other kwargs are ignored on purpose
        return Binary.content_image(args,kwargs)
