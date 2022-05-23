import jwt

from odoo import api, http, models
from odoo.http import request, content_disposition, Response


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_jwt(cls):
        if not request.params.get('jwt'):
            raise http.AuthenticationError("The JWT is required")
        else:
            payload = jwt.decode(request.params['jwt'], request.env.cr.dbname + "longlml", algorithms=["HS256"])
            if not payload.get('uid'):
                raise http.AuthenticationError("The JWT is required")
            request.uid = payload['uid']
