from uuid import getnode as getmac
from getpass import getuser
import os
from odoo.tools import config as odoo_config

token_mode = odoo_config.get('token_mode', 'env')
if token_mode == 'mac':
    token = getmac()
elif token_mode == 'env':
    default_token = 'odoo-token:long-bui'
    odoo_config_token = odoo_config.get('host_token', default_token)
    token = os.getenv('WT_TOKEN', odoo_config_token)
else:
    raise ValidationError("The token mode is incorrect")
identification_cpu = "%s-%s" % (token, getuser())
