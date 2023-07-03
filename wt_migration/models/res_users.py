import logging
from datetime import datetime

from odoo import models, fields, _
from odoo.tools import ormcache
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = "res.users"

    account_id = fields.Char(string="account ID")

    @ormcache('self')
    def get_jira_token(self):
        return self.env['token.storage'].get_token("jira_" + str(self.login or self.partner_id.email))

    def set_jira_token(self, value):
        self.env['token.storage'].set_token("jira_" + str(self.login or self.partner_id.email), value)
        self.env['token.storage'].clear_caches()
        self.load_jira_projects()

    def load_jira_projects(self):
        fetch_ok = False
        company_domain = [('company_id', 'in', self.env.user.company_ids.ids)]
        existing_migrations = self.env['wt.migration'].sudo().search(company_domain)
        if existing_migrations:
            to_fetch_projects = self.env['wt.project'].search(company_domain)
            for migration in existing_migrations:
                    to_fetch_projects |= migration.load_projects()
                    fetch_ok = True
            if not fetch_ok:
                raise UserError(_("The Token is invalid, please check again"))
            self.env['ir.config_parameter'].sudo().set_param('latest_unix', int(datetime.now().timestamp() * 1000))

    def token_exists(self):
        existing_token_users = self.env['res.users']
        for user in self:
            try:
                user.get_jira_token()
                existing_token_users |= user
            except:
                continue
        return existing_token_users 

    @ormcache('migration')
    def token_exists_by_migration(self, migration):
        users = self.env['res.users']
        existing_tokens = self.token_exists()
        errors = []
        unaccess_users = migration.get_unaccess_token_users()
        for user in existing_tokens:
            if user not in unaccess_users:
                try:
                    migration.with_user(user)._get_permission()
                    users |= user
                except Exception as e:
                    migration.add_unaccess_token_users(user)
                    error = "Unaccecss TOKEN: %s >> %s"%(user.name, str(e))
                    _logger.error(error)
                    errors.append(error)
        if len(errors):
            error_msg = "\n".join(errors)
            raise UserError(error_msg)
        return users

    def token_clear_cache(self):
        self.env['token.storage'].clear_caches()