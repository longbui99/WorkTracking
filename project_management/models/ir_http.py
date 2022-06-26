import jwt

from odoo import api, http, models, exceptions
from odoo.http import request, content_disposition, Response
from odoo.addons.project_management.utils.error_tracking import handling_exception


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @handling_exception
    def _auth_method_jwt(cls):
        try:
            if not request.params.get('jwt'):
                raise exceptions.AccessDenied("The JWT uid is required")
            else:
                payload = jwt.decode(request.params['jwt'], request.env.cr.dbname + "longlml", algorithms=["HS256"])
                if not payload.get('uid'):
                    raise exceptions.AccessDenied("The JWT uid is required")
                if not request.env['user.access.code'].sudo().search_count([('key', '=', payload.get('token', False))]):
                    raise exceptions.AccessDenied("The JWT is incorrect")
                request.uid = payload['uid']
        except Exception as e:
            return http.Response(str(e), content_type='text/http', status=404)
