from odoo import models

class WorkTimeLog(models.Model):
    _inherit = "work.time.log"

    def delete_work_logs_on_host(self, ):
        if self.host_id._type == "odoo":
            rpc = self.host_id.make_rpc_agent()
            self = self.with_context(rpc=rpc)
        return super().delete_work_logs_on_host()
