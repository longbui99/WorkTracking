# Copyright © 2021 Novobi, LLC
# See LICENSE file for full copyright and licensing details.

import io
from odoo import http, fields, _
from odoo.http import request, content_disposition
import json

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter
try:
    import xlrd

    try:
        from xlrd import xlsx
    except ImportError:
        xlsx = None
except ImportError:
    xlrd = xlsx = None


class ListViewItemExport(http.Controller):

    @http.route(['/lb-project-management/export'], type='http', methods=['POST'])
    def download_xlsx(self, data):
        data = json.loads(data)
        model, res_id, call_method = data.get('model', False), data.get('res_id', False), data.get('method', False)
        record = request.env[model].browse(res_id)
        file_name = content_disposition(record.display_name)
        if hasattr(record, 'get_report_file_name'):
            file_name = content_disposition(record.get_report_file_name())
        response = request.make_response(None, headers=[('Content-Type', 'application/vnd.ms-excel'),
                                                        ('Content-Disposition', file_name)])
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        if hasattr(record, call_method):
            getattr(record, call_method)(workbook)
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
        return response
