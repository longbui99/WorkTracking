import json
import traceback
import functools
import logging
from odoo.http import request, Response
_logger = logging.getLogger(__name__)

def log_error():
    error_str = traceback.format_exc()
    params = json.dumps(request.params, indent=2)
    error_str += params
    _logger.error(error_str)


def handling_req_res(func):
    @functools.wraps(func)
    def wrapper_func(*args, **kwargs):
        try:
            request.env.user._update_last_login()
            res = func(*args, **kwargs)
            if 400 <= res.status_code < 600:
                log_error()
            return res
        except Exception as e:
            log_error()
            return Response(str(e), content_type='application/json', status=404)
    return wrapper_func