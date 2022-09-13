from . import controllers
from . import models
from . import wizard

from odoo import SUPERUSER_ID, api



def post_init_hook(cr, registry):
    print("-------------------------------------------------")
    cr.execute("""
        CREATE TABLE IF NOT EXISTS token_cache ( key VARCHAR UNIQUE, value VARCHAR);
        CREATE INDEX IF NOT EXISTS token_cache_index ON token_cache USING HASH (key);
    """)