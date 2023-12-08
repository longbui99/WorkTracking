from odoo import fields, http, _
from odoo.http import request


class DependencyPlanning(http.Controller):
    
    @http.route('/web/planning/dependencies', type='http', auth="none")
    def portal_order_page(self):
        return request.render('work_abc_management.dependency_planning', {})

    @http.route('/web/planning/dependencies/fetch/<string:param_key>', type='json', methods=['POST'],  auth="none", csrf=False)
    def portal_fetch_flow_data(self, param_key):
        param = request.env['work.param'].sudo().search([('key', '=', param_key)])
        if not param:
            res = {}
        else:
            res = request.env[param.model].launch_flow(param)
        return res