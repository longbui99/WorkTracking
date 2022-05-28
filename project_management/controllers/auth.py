# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import jwt
import json
import string
import random

from odoo import http, _, exceptions
from odoo.http import request

IDEMPOTENCY_LENGTH = 10


def generate_idempotency_key():
    characters = string.ascii_uppercase + string.digits
    return ''.join([random.choice(characters) for _ in range(IDEMPOTENCY_LENGTH)])


class Auth(http.Controller):
    @http.route(['/web/login/jwt'], methods=['GET', 'POST'], cors="*", type="http", auth="none", csrf=False)
    def auth_login_encrypt(self):
        res = {}
        try:
            uid = request.env['res.users'].authenticate(request.env.cr.dbname,
                                                    request.params.get('login', ''),
                                                    request.params.get('password', ''),
                                                    {'interactive': False})
        except exceptions.AccessDenied as e:
            return http.Response(str(e), content_type='text/http', status=404)
        if uid:
            token = generate_idempotency_key()
            request.env['user.access.code'].sudo().create({'key': token, 'uid': uid})
            response = jwt.encode({"uid": uid, "token": token}, request.env.cr.dbname + "longlml", algorithm="HS256")
            if not (isinstance(response, str)):
                response = response.decode('utf-8')
            res = {'data': response, "name": request.env.user.sudo().browse(uid).name}
        return http.Response(json.dumps(res), content_type='application/json', status=200)
