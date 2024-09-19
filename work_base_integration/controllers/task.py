import json
from odoo import http, _
from odoo.http import request
from odoo.addons.work_abc_management.controllers.task import WorkTask
from odoo.addons.work_abc_management.controllers.auth import Auth
from odoo.addons.work_abc_management.utils.error_tracking import handling_req_res
from odoo.addons.web.controllers.main import Binary
import logging
_logger = logging.getLogger(__name__)

class WorkTaskHost(WorkTask):

    def _fill_default_type_url(self, records):
        default_host_url = False
        for record in records:
            if not record['type_url']:
                if not default_host_url:
                    default_type_url = request.env['ir.config_parameter'].sudo().get_param('default.type.url')
                record['type_url'] = default_type_url
        return records

    def _get_work_log(self, log): 
        log.mapped('task_id.host_id.host_image_url')
        res = super()._get_work_log(log)
        res['exported'] = log.export_state
        res['host_image_url'] = log.task_id.host_id.host_image_url
        return res

    def _get_work_logs(self, log_ids):
        res = super()._get_work_logs(log_ids)
        return self._fill_default_type_url(res)
    
    def _get_task_data(self, task):
        res = super()._get_task_data(task)
        res['host_image_url'] = task.host_id.host_image_url
        return res

    def _get_tasks_data(self, tasks):
        res = super()._get_tasks_data(tasks)
        return self._fill_default_type_url(res)
    
    @handling_req_res
    @http.route(['/management/task/search', 
                 '/management/issue/search'], type="http", cors="*", methods=['POST'], auth='jwt', csrf=False)
    def search_task_post(self):
        # try:
        kwargs = request.share_params
        res = super().search_task_post()
        offset = int(kwargs.get('offset', 0))
        if res.data == b'[]' and offset == 0:
            task_ids = request.env['work.base.integration'].query_candidate_task(kwargs.get('query', ''))
            if task_ids:
                data = self._get_task(task_ids)
                return http.Response(json.dumps(data), content_type='application/json', status=200)
        # except Exception as e:
        #     return http.Response(str(e), content_type='application/json', status=400)
        return res

    @handling_req_res
    @http.route(['/management/task/search/<string:keyword>',
                 '/management/issue/search/<string:keyword>'], type="http", cors="*", methods=['GET'],
                auth='jwt', csrf=False)
    def search_task(self, keyword, **kwargs):
        try:
            res = super().search_task(keyword, **kwargs)
            offset = int(kwargs.get('offset', 0))
            if res.data == b'[]' and offset == 0:
                task_ids = request.env['work.base.integration'].query_candidate_task(keyword)
                if task_ids:
                    data = self._get_task(task_ids)
                    return http.Response(json.dumps(data), content_type='application/json', status=200)
        except Exception as e:
            return http.Response(str(e), content_type='application/json', status=400)
        return res

    @handling_req_res
    @http.route(['/management/task/fetch/<int:task_id>',
                 '/management/issue/fetch/<int:task_id>'], type="http", cors="*", methods=["GET"],
                auth="jwt", csrf=False)
    def fetch_task_from_host(self, task_id, **kwargs):
        if not task_id:
            return Exception("Need to provide task id")
        task_id = request.env['work.task'].browse(task_id)
        task_id.import_task_work()
        data = self._get_task(task_id)
        return http.Response(json.dumps(data[0]), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/work-log/export',
                 '/management/issue/work-log/export'], type="http", cors="*", methods=["POST"], auth="jwt", csrf=False)
    def export_task_to_host(self, **kwargs):
        time_ids = request.env['work.time.log'].browse(request.share_params.get('exportIds', [])).exists().force_export()
        data = self._get_work_logs(time_ids)
        return http.Response(json.dumps(data), content_type='application/json', status=200)

    @handling_req_res
    @http.route(['/management/task/work-log/compare',
                 '/management/issue/work-log/compare'], type="http", cors="*", methods=["POST"], auth="jwt", csrf=False)
    def compare_log_to_host(self, **kwargs):
        data = request.env['work.time.log'].browse(request.share_params.get('ids', [])).compare_with_external()
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
