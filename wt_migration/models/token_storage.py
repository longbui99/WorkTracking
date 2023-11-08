import logging

from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.addons.wt_sdk.cache import identification_cpu

CRYPTO_KEY = bytes(identification_cpu[:16], 'utf-8')

_logger = logging.getLogger(__name__)


class TokenStorage(models.Model):
    _name = 'token.storage'
    _description = 'Token Storage'
    _auto = False

    @api.model
    def pad(self, s, bs):
        return s + (bs - len(s) % bs) * chr(bs - len(s) % bs)

    @api.model
    def unpad(self, s):
        return s[:-ord(s[len(s) - 1:])]

    def init_token_storage(self):
        self.env.cr.execute("""
                CREATE TABLE IF NOT EXISTS token_cache ( key VARCHAR UNIQUE, value VARCHAR);
                CREATE INDEX IF NOT EXISTS token_cache_index ON token_cache USING HASH (key);
            """)

    def get_token(self, key):
        self.env.cr.execute(f"SELECT value FROM token_cache WHERE key = '{key}'")
        res = self.env.cr.dictfetchone()
        if not res:
            raise UserError("Cannot find token for the user: " + self.env.user.display_name)
        try:
            b64 = b64decode(res['value'])
            new_iv, new_ct = b64[:AES.block_size], b64[AES.block_size:]
            cipher = AES.new(CRYPTO_KEY, AES.MODE_CBC, new_iv)
            plan_text = cipher.decrypt(new_ct)
            result = unpad(plan_text, AES.block_size).decode('utf-8')
        except:
            raise UserError("Cannot find token for the user: " + self.env.user.display_name)
        return result

    def set_token(self, key, value):
        _logger.info(_("Migration token for user %s is updated by user id %s" % (key, self.env.user.id)))
        value = bytes(value, 'utf-8')
        cipher = AES.new(CRYPTO_KEY, AES.MODE_CBC)
        value = pad(value, AES.block_size)
        ct_bytes = cipher.encrypt(value)
        result = b64encode(cipher.iv + ct_bytes).decode('utf-8')
        insert_stmt = "INSERT INTO token_cache (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s"
        self.env.cr.execute(insert_stmt, (key, result, result))
        return result
