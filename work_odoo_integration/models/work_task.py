
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class WorkProject(models.Model):
    _inherit = "work.task"

    def import_task_host(self):
        if self.host_id._type == "odoo":
            res = {'task': self.mapped('id_onhost')}
            return self.host_id._search_load(res)
        else:
            return super().import_task_host()

    def export_time_log_to_host(self):
        if self.host_id._type == "odoo":
            rpc = self.host_id.make_rpc_agent()
            self = self.with_context(rpc=rpc)
        return super().export_time_log_to_host()
