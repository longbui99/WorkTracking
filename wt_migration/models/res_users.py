import logging
from datetime import datetime

from odoo import models, fields, _
from odoo.tools import ormcache
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = "res.users"

    account_id = fields.Char(string="account ID")

    @ormcache('self', 'migration')
    def get_token(self, migration):
        key = migration.get_prefix() + str(self.id)
        return self.env['token.storage'].get_token(key)

    def set_token(self, migration, value):
        key = migration.get_prefix() + str(self.id)
        self.env['token.storage'].set_token(key, value)
        self.env['token.storage'].clear_caches()
        self.load_projects(migration)
        self.env.cr.commit()

    def load_projects(self, existing_migration):
        fetch_ok = False
        if existing_migration:
            to_fetch_projects = self.env['wt.project'].search(['|', ('wt_migration_id', '=', existing_migration.id), ('company_id', '=', existing_migration.company_id.id)])
            to_fetch_projects |= existing_migration.load_projects()
            fetch_ok = True
            if not fetch_ok:
                raise UserError(_("The Token is invalid, please check again"))
            self.env['ir.config_parameter'].sudo().set_param('latest_unix', int(datetime.now().timestamp() * 1000))

    def token_exists(self, migration):
        existing_token_users = self.env['res.users']
        for user in self:
            try:
                user.get_token(migration)
                existing_token_users |= user
            except:
                continue
        return existing_token_users 

    @ormcache('migration')
    def token_exists_by_migration(self, migration):
        users = self.env['res.users']
        existing_tokens = self.token_exists(migration)
        errors = []
        unaccess_users = migration.get_unaccess_token_users()
        for user in existing_tokens:
            if user not in unaccess_users:
                try:
                    # migration.with_user(user)._get_permission()
                    users |= user
                except Exception as e:
                    # migration.add_unaccess_token_users(user)
                    error = "Unaccecss TOKEN: %s >> %s"%(user.name, str(e))
                    _logger.error(error)
                    errors.append(error)
        if len(errors):
            error_msg = "\n".join(errors)
            _logger.error(error_msg)
        return users

    def token_clear_cache(self):
        self.env['token.storage'].clear_caches()
