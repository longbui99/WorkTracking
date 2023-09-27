
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class WtProject(models.Model):
    _inherit = "wt.issue"

    def import_issue_wt(self):
        if self.wt_migration_id.migration_type == "odoo":
            res = {'issue': self.mapped('wt_id')}
            return self.wt_migration_id._search_load(res)
        else:
            return super().import_issue_wt()

    def export_time_log_to_wt(self):
        if self.wt_migration_id.migration_type == "odoo":
            rpc = self.wt_migration_id.make_rpc_agent()
            self = self.with_context(rpc=rpc)
        return super().export_time_log_to_wt()
