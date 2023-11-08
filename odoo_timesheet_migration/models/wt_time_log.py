from odoo import models

class WtTimeLog(models.Model):
    _inherit = "wt.time.log"

    def delete_work_logs_on_server(self, ):
        if self.wt_migration_id.migration_type == "odoo":
            rpc = self.wt_migration_id.make_rpc_agent()
            self = self.with_context(rpc=rpc)
        return super().delete_work_logs_on_server()
