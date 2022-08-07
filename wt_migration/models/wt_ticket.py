import datetime
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class JiraProject(models.Model):
    _inherit = "wt.ticket"

    wt_migration_id = fields.Many2one('wt.migration', string='Task Migration')
    status_value = fields.Char(related='status_id.wt_key', store=True)
    last_export = fields.Datetime("Last Export Time")
    auto_export_success = fields.Boolean(string="Export Successful?", default=True)
    sprint_key = fields.Integer(related='sprint_id.id_on_wt', store=True, default=0.0)
    wt_id = fields.Integer(string="Task ID")

    def export_time_log_to_wt(self):
        for record in self:
            record.wt_migration_id.export_time_log(record)
            record.last_export = datetime.datetime.now()

    def export_ac_to_wt(self):
        for record in self:
            record.wt_migration_id.export_acceptance_criteria(record)

    def import_ticket_wt(self):
        res = {'ticket': self.mapped('ticket_key')}
        self.wt_migration_id._search_load(res)

    def action_done_work_log(self, values={}):
        res = super().action_done_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', self.env.user.id)]).mapped('auto_export_work_log')):
                res.filtered(lambda r: r.wt_migration_id.auto_export_work_log).export_time_log_to_wt()
            res.write({'last_export': datetime.datetime.now()})
            self.write({'auto_export_success': True})
        except Exception as e:
            _logger.warning(e)
            self.write({'auto_export_success': False})
        return res

    def action_manual_work_log(self, values={}):
        self.ensure_one()
        res, time_log_ids = super().action_manual_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', res.env.user.id)]).mapped('auto_export_work_log')):
                if res.wt_migration_id.auto_export_work_log:
                    res.wt_migration_id.add_time_logs(res, time_log_ids)
                    res.last_export = datetime.datetime.now()
            self.write({'auto_export_success': True})
        except Exception as e:
            _logger.warning(e)
            self.write({'auto_export_success': False})
        return res

    def import_work_logs(self):
        for record in self:
            record.wt_migration_id.with_delay().load_work_logs(record)

    @api.model
    def re_export_work_log(self):
        self.search([('auto_export_success', '=', False)]).action_done_work_log({})

    @api.model
    def create(self, values):
        res = super().create(values)
        res.last_export = datetime.datetime.now()
        return res

    def get_acceptance_criteria(self, values={}):
        res = []
        for record in self.ac_ids:
            res.append({
                'id': record.id,
                'content': record.wt_raw_name,
                'is_header': record.is_header,
                'checked': record.checked,
                'sequence': record.sequence,
                'need_compile': True
            })
        return res

    def export_ticket_to_server(self, values={}):
        if values.get('mode', {}).get('worklog', False):
            self.export_time_log_to_wt()
        if values.get('mode', {}).get('ac', False):
            self.export_ac_to_wt()

    def batch_export(self, pivot_time):
        self.write({'last_export': pivot_time})
        self.export_time_log_to_wt()

    def render_batch_update_wizard(self):
        action = self.env.ref("wt_migration.export_work_log_action_form").read()[0]
        action["context"] = {'default_ticket_ids': self.ids}
        return action

    def get_search_ticket_domain(self, res, employee):
        if 'jql' in res:
            return []
        else:
            return super().get_search_ticket_domain(res, employee)