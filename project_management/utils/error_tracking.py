import traceback
import functools
import logging
from odoo.http import request, Response
_logger = logging.getLogger(__name__)


def handling_req_res(func):
    @functools.wraps(func)
    def wrapper_func(*args, **kwargs):
        try:
            request.env.user._update_last_login()
            return func(*args, **kwargs)
        except Exception as e:
            _logger.error(traceback.format_exc())
            return Response(str(e), content_type='application/json', status=404)
    return wrapper_func