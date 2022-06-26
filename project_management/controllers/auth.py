# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import jwt
import json
import string
import random

from odoo import http, _, exceptions
from odoo.http import request
from odoo.addons.project_management.utils.error_tracking import handling_exception

IDEMPOTENCY_LENGTH = 10


def generate_idempotency_key():
    characters = string.ascii_uppercase + string.digits
    return ''.join([random.choice(characters) for _ in range(IDEMPOTENCY_LENGTH)])

def generate_jwt(uid, token=False):
    if not token:
        token = generate_idempotency_key()
    response = jwt.encode({"uid": uid, "token": token}, request.env.cr.dbname + "longlml", algorithm="HS256")
    if not (isinstance(response, str)):
        response = response.decode('utf-8')
    return response


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
            response = generate_jwt(uid)
            calendar = request.env["hr.employee"].sudo().search([('user_id','=', uid)]).resource_calendar_id
            res = {
                'data': response, 
                "name":request.env.user.sudo().browse(uid).name,
                "resource": {
                    "hrs_per_day": calendar.hours_per_day or 8,
                    "days_per_week": len(set(calendar.attendance_ids.mapped('dayofweek'))) or 5
                }
            }
        return http.Response(json.dumps(res), content_type='application/json', status=200)

    @handling_exception
    @http.route(['/web/login/jwt/new-code'], methods=['GET', 'POST'], cors="*", type="http", auth="jwt", csrf=False)
    def fetch_new_code(self, **kwargs):
        res = {}
        token = generate_idempotency_key()
        jwt = generate_jwt(request.env.user.id, token)
        payload = jwt.decode(request.params['jwt'], request.env.cr.dbname + "longlml", algorithms=["HS256"])
        code = request.env['user.access.code'].sudo().search_count([('key', '=', payload.get('token', False))])     
        code.write({'key': token})
        res['jwt'] = jwt
        return http.Response(json.dumps(res), content_type='application/json', status=200)

