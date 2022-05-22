# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from werkzeug import urls
from werkzeug.exceptions import NotFound, Forbidden
import jwt
import json

from odoo import http, _
from odoo.http import request
from odoo.osv import expression
from odoo.tools import consteq, plaintext2html
from odoo.addons.mail.controllers import mail
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError, UserError


class Auth(http.Controller):
    @http.route(['/web/login/jwt'], methods=['GET', 'POST'], cors="*", type="http", auth="none", csrf=False)
    def auth_login_encrypt(self):
        res = {"data": ""}
        uid = request.env['res.users'].authenticate(request.env.cr.dbname,
                                                    request.params.get('login', ''),
                                                    request.params.get('password', ''),
                                                    {'interactive': False})
        if uid:
            response = jwt.encode({"uid": uid}, request.env.cr.dbname + "longlml", algorithm="HS256")
            res = {'data': response}
        return http.Response(json.dumps(res), content_type='application/json', status=200)
