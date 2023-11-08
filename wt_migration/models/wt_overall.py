from collections import defaultdict
import logging
import traceback
from datetime import datetime


from odoo import api, fields, models, _
from odoo.osv import expression
from odoo.exceptions import UserError

from odoo.addons.project_management.models.wt_time_logging import WtTimeLog as WtTimeLogBase

_logger = logging.getLogger(__name__)


class WtStatus(models.Model):
    _inherit = "wt.status"

    wt_key = fields.Char(string='Task Key')
    wt_migration_id = fields.Many2one("wt.migration", string="Migration", ondelete="cascade")

class WtType(models.Model):
    _inherit = "wt.type"
    wt_migration_id = fields.Many2one("wt.migration", string="Migration", ondelete="cascade")

class WtTimeLog(models.Model):
    _inherit = "wt.time.log"

    id_on_wt = fields.Integer(string='ID on Task')
    is_exported = fields.Boolean(string="Is Exported?", default=False)
    wt_create_date = fields.Datetime(string="Wt Create On")
    wt_write_date = fields.Datetime(string="Wt Update On")
    export_state = fields.Integer( string="Export State", default=False)
    capture_export_description = fields.Char(string="Capture Export Description")
    capture_export_duration = fields.Integer(string="Capture Export Duration")
    capture_export_start_date = fields.Datetime(string="Capture Export Datetime")
    # [
    #     (0, "Unexported"),
    #     (1, "Exported"),
    #     (3, "Exported But Description Change"),
    #     (5, "Exported But Duration Change"),
    #     (7, "Exported But Start Date Change"),
    #     (15, "Exported But All Changes"),
    #     (12, "Exported But Duration + Start Date Changes"),
    #     (8, "Exported But Duration + Description Changes"),
    #     (10, "Exported But Description + Start Date Changes"),
    # ],

    def batch_export(self, pivot_time):
        issue_ids = self.mapped('issue_id')
        issue_ids.write({'last_export': pivot_time})
        issue_ids.export_time_log_to_wt()

    def render_batch_update_wizard(self):
        action = self.env.ref("wt_migration.export_work_log_action_form").read()[0]
        action["context"] = {'default_time_log_ids': self.ids}
        return action
    
    def _get_export_state(self, values):
        self.ensure_one()
        value = 0
        if 'issue_id' in values:
            return 0
        if 'start_date' in values:
            if self.capture_export_start_date != values['start_date']:
                value += 7
        elif self.capture_export_start_date != self.start_date:
            value += 7
        if 'duration' in values:
            if self.capture_export_duration != values['duration']:
                value += 5
        elif self.capture_export_duration != self.duration:
            value +=7
        if 'description' in values:
            if self.capture_export_description != values['description']:
                value += 3
        elif self.capture_export_description != self.description:
            value += 3
        return value or 1

    def delete_work_logs_on_server(self, ):
        log_by_issue = defaultdict(lambda: self.env['wt.time.log'])
        for log in self:
            log_by_issue[log.issue_id] |= log
        for issue, logs in log_by_issue.items():
            issue.wt_migration_id.delete_time_logs(issue, logs)

    def write(self, values):
        if 'issue_id' in values and not self._context.get('bypass_auto_delete'):
            to_delete_logs = self.filtered(lambda r: r.issue_id.id != values['issue_id'] and r.export_state)
            _logger.info(to_delete_logs) 
            if to_delete_logs:
                to_delete_logs.delete_work_logs_on_server()
                self.env.cr.execute("""
                    UPDATE wt_time_log 
                    SET 
                    capture_export_description = 0, 
                    capture_export_duration = 0, 
                    capture_export_start_date = '1970-01-01',
                    export_state = 0,
                    id_on_wt = 0
                    WHERE id in %(ids)s
                """, {'ids': tuple(to_delete_logs.ids)})
        res = True 
        self.rounding(values)
        if type(values.get('start_date', None)) in (int, float):
            values['start_date'] = datetime.fromtimestamp(values['start_date'])
        # END  PROJECT MANAGEMENT
        if type(values.get('description', None)) == str:
            values['description'] = values['description'].strip()
        if not self._context.get("bypass_cross_user"):
            user = self.env.user 
            other_logs = self.filtered(lambda log: log.user_id != user)
            if other_logs:
                raise UserError("You cannot update work log of other user")
        to_update_records = self
        if 'export_state' not in values and not self._context.get("bypass_exporting_check"):
            processed_records = self.env['wt.time.log']
            employee = self.env.user.employee_id
            if employee.auto_export_work_log:
                for log in self:
                    if log.issue_id.wt_migration_id.auto_export_work_log:
                        try:
                            log.issue_id.wt_migration_id.export_specific_log(log.issue_id, log)
                            processed_records |= log
                        except Exception as e:
                            _logger.error(e)
            exported_values = {**values, **{'export_state': 1}}
            if processed_records:
                super(WtTimeLog, processed_records.with_context(bypass_exporting_check=True)).write(exported_values)
            exported_logs = (self-processed_records).filtered(lambda r: r.export_state >= 1)
            if exported_logs:
                log_by_state = defaultdict(lambda: self.env['wt.time.log'])
                for log in exported_logs:
                    state = log._get_export_state(values)
                    log_by_state[state] |= log
                for state, logs in log_by_state.items():
                    exported_values['export_state'] = state
                    super(WtTimeLog, logs.with_context(bypass_exporting_check=True)).write(exported_values)
            to_update_records -= (processed_records | exported_logs)
        if to_update_records:
            res = super(WtTimeLog, to_update_records).write(values)

        return res

    def force_export(self):
        issues = dict()
        for record in self:
            if record.issue_id in issues:
                issues[record.issue_id] |= record
            else:
                issues[record.issue_id] = record
            record.update({
                'capture_export_description': record.description,
                'capture_export_duration': record.duration,
                'capture_export_start_date': record.start_date
            })
        for issue in issues.keys():
            issue.wt_migration_id.export_specific_log(issue, issues[issue])
        self.export_state = 1
        return self

    def unlink(self):
        try:
            if self.id_on_wt:
                self.issue_id.wt_migration_id.delete_time_logs(self.issue_id, self)
        except:
            pass
        return super().unlink()

    def load_history_domain(self):
        domain = super().load_history_domain()
        if self._context.get('tracking') == "unexported":
            domain = expression.AND([[('export_state', '=', 1)], domain])
        if self._context.get('tracking') == "exported":
            domain = expression.AND([[('export_state', '!=', 1)], domain])
        return domain
    
    def compare_with_external(self, keys={'start_date', 'duration', 'description'}):
        if self:
            res = defaultdict(dict)
            for log in self:
                for key in keys:
                    current = getattr(log, key)
                    exported = getattr(log, 'capture_export_%s'%key)
                    if isinstance(current, datetime):
                        current = current.isoformat()
                        exported = exported.isoformat()
                    if current == exported:
                        continue
                    res[log.id][key] = (current, exported)
            
            # logs_by_migration = defaultdict(lambda: self.env['wt.time.log'])
            # for log in self:
            #     logs_by_migration[log.issue_id.migration_id] |= log
            # wt_datas = []
            # for migration, logs in logs_by_migration.items():
            #     wt_datas.append(migration.load_work_log_by_ids_raw(logs.mapped('id_on_wt'), self.env.user))
            # raw_log_by_wt_id = dict()
            # for log in wt_datas:
            #     raw_log_by_wt_id[log['id_on_wt']] = log
            # res = defaultdict(dict)
            # for log in self:
            #     res[log.id] = None
            #     if raw_log_by_wt_id(log.id_on_wt):
            #         res[log.id] = {}
            #         for key in keys:
            #             res[log.id][key] = (log.key, raw_log_by_wt_id[log.id_on_wt].get(key))
            return res

    def action_export_work_logs(self):
        logs_by_user = defaultdict(lambda: self.env['wt.time.log'])
        for log in self:
            if log.export_state != 1:
                logs_by_user[log.user_id] |= log

        for user, logs in logs_by_user.items():
            logs.with_user(user).force_export()


def write(self, values):
    return super(WtTimeLogBase, self).write(values)

WtTimeLogBase.write = write