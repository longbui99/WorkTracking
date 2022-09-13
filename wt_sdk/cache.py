import os
from odoo import tools
from odoo.tools.config import _get_default_datadir

TOKEN_DIR = _get_default_datadir() + '/token/'
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


token = TokenCache(TOKEN_PATH)
