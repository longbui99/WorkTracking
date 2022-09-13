import os
from odoo import tools
from odoo.tools.appdirs import user_data_dir
from odoo import SUPERUSER_ID, api

TOKEN_DIR = user_data_dir() + '/token/'
if not os.path.exists(TOKEN_DIR):
    os.mkdir(TOKEN_DIR)

TOKEN_PATH = TOKEN_DIR + (os.getenv('TOKEN_FILENAME') or 'token.txt' )

class TokenCache:
    def __init__(self, file_path):
        if not os.path.exists(file_path):
            open(file_path, 'x').close()
        os.chmod(file_path, 600)
        self.file_path = file_path
        self.tokens = dict()
        self._load_tokens()

    def _load_tokens(self):
        if self.file_path:
            with open(self.file_path, 'r') as f:
                tokens = f.readlines()
                for token in tokens:
                    spliting_token = token.split(':')
                    self.tokens[spliting_token[0]] = spliting_token[1]

    def _store_tokens(self):
        storing_string = []
        for key, value in self.tokens.items():
            storing_string.append(key + ":" + value)
        with open(self.file_path, 'w') as f:
            f.writelines(storing_string)
            f.close()

    def _clear_tokens(self):
        with open(self.file_path, 'w') as f:
            f.write('')
            f.close()
    
    def _check_token(self, key, value):
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError('The token key and value must be string type')
        if ':' in key or ':' in value:
            raise ValueError("""The key and value must not contain ":" character!""")
        return True

    def _update_token(self, key, value):
        if self.file_path:
            self._check_token(key, value)
            self.tokens[key] = value
            self._store_tokens()

    def get_token(self, key):
        if key not in self.tokens:
            raise KeyError("Cannot find token for the key: " + str(key))
        return self.tokens[key]

    def set_token(self, key, value):
        self._update_token(key, value)

class TokenStorage(TokenCache):

    def get_token(self, key, odoo_model):
        odoo_model.env.cr.execute(f"SELECT value FROM token_cache WHERE key = '{key}'")
        res = odoo_model.env.cr.dictfetchone()
        if not res:
            raise KeyError("Cannot find token for the key: " + str(key))
        return res.get('value')

    def set_token(self, key, value, odoo_model):
        odoo_model.env.cr.execute(f"""
        INSERT INTO token_cache (key, value) VALUES ('{key}','{value}')
        ON CONFLICT (key) DO
        UPDATE SET value = '{value}'""")

try:
    token = TokenCache(TOKEN_PATH)
except PermissionError as e:
    token = TokenStorage(False)
