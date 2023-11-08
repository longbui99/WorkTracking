import logging
from datetime import datetime

from odoo import models, fields, _
from odoo.tools import ormcache
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = "res.users"

    account_id = fields.Char(string="account ID")

    @ormcache('self', 'host')
    def get_token(self, host):
        key = host.get_prefix() + str(self.id)
        return self.env['token.storage'].get_token(key)

    def set_token(self, host, value):
        key = host.get_prefix() + str(self.id)
        self.env['token.storage'].set_token(key, value)
        self.env['token.storage'].clear_caches()
        self.load_projects()
        self.env.cr.commit()

    def load_projects(self, existing_):
        fetch_ok = False
        if existing_:
            to_fetch_projects = self.env['work.project'].search(['|', ('host_id', '=', existing_.id), ('company_id', '=', existing_.company_id.id)])
            to_fetch_projects |= existing_.load_initial_projects()
            fetch_ok = True
            if not fetch_ok:
                raise UserError(_("The Token is invalid, please check again"))

    def token_exists(self, ):
        existing_token_users = self.env['res.users']
        for user in self:
            try:
                user.get_token()
                existing_token_users |= user
            except:
                continue
        return existing_token_users 

    @ormcache('host')
    def token_exists_by_host(self, host):
        users = self.env['res.users']
        existing_tokens = self.token_exists()
        errors = []
        unaccess_users = host.get_unaccess_token_users()
        for user in existing_tokens:
            if user not in unaccess_users:
                try:
                    # .with_user(user)._get_permission()
                    users |= user
                except Exception as e:
                    # .add_unaccess_token_users(user)
                    error = "Unaccecss TOKEN: %s >> %s"%(user.name, str(e))
                    _logger.error(error)
                    errors.append(error)
        if len(errors):
            error_msg = "\n".join(errors)
            _logger.error(error_msg)
        return users

    def token_clear_cache(self):
        self.env['token.storage'].clear_caches()
