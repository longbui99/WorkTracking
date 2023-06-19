from . import controllers
from . import models
from . import wizard

from odoo import SUPERUSER_ID, api


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['token.storage'].init_token_storage()
