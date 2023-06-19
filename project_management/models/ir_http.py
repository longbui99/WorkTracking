import jwt
import json
from odoo import api, http, models, exceptions
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_jwt(cls):
        if len(request.params) == 0:
            request.params = json.loads(request.httprequest.data)
        if not request.params.get('jwt'):
            raise exceptions.AccessDenied("The JWT uid is required")
        else:
            payload = jwt.decode(request.params['jwt'], request.env.cr.dbname + "longlml", algorithms=["HS256"])
            if not payload.get('uid'):
                raise exceptions.AccessDenied("The JWT uid is required")
            if not request.env['user.access.code'].sudo().search_count([('key', '=', payload.get('token', False))]):
                raise exceptions.SessionExpiredException("The JWT is incorrect")
            request.uid = payload['uid']
