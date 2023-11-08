from . import controllers
from . import models
from . import wizard

from odoo import SUPERUSER_ID, api


def post_init_hook(env):
    env['token.storage'].init_token_storage()
