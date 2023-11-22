import jwt
import json
from odoo import models, exceptions
from odoo.http import request, SessionExpiredException

import logging

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_jwt(cls):
        params = request.get_http_params()
        if len(params) == 0:
            args = json.loads(request.httprequest.data)
            request.http.args.update(args)
            params.update(args)
        if not params.get('jwt'):
            raise exceptions.AccessDenied("The JWT uid is required")
        else:
            payload = jwt.decode(params['jwt'],"WorkTrackinglonglml", algorithms=["HS256"])
            if not payload.get('uid'):
                raise exceptions.AccessDenied("The JWT uid is required")
            # if not request.env['user.access.code'].sudo().search_count([('key', '=', payload.get('token', False))]):
            #     raise SessionExpiredException("The JWT is incorrect")
            request.update_env(user=payload['uid'])
