import datetime
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class JiraProject(models.Model):
    _inherit = "jira.ticket"

    jira_migration_id = fields.Many2one('jira.migration', string='Jira Migration')
    status_value = fields.Char(related='status_id.jira_key', store=True)
    last_export = fields.Datetime("Last Export Time")

    def export_time_log_to_jira(self):
        try:
            for record in self:
                record.jira_migration_id.export_time_log(record)
                record.last_export = datetime.datetime.now()
        except Exception as e:
            _logger.warning(e)

    def export_ac_to_jira(self):
        try:
            for record in self:
                record.jira_migration_id.export_acceptance_criteria(record)
        except Exception as e:
            _logger.warning(e)

    def import_ticket_jira(self):
        for record in self:
            record.jira_migration_id._search_load('ticket', [record.ticket_key])

    def action_done_work_log(self, values={}):
        res = super().action_done_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', self.env.user.id)]).mapped('auto_export_work_log')):
                res.filtered(lambda r: r.jira_migration_id.auto_export_work_log).export_time_log_to_jira()
            res.write({'last_export': datetime.datetime.now()})
        except Exception as e:
            _logger.warning(e)
        return res

    def action_manual_work_log(self, values={}):
        self.ensure_one()
        res, time_log_ids = super().action_manual_work_log(values)
        try:
            if any(res.env['hr.employee'].search([('user_id', '=', res.env.user.id)]).mapped('auto_export_work_log')):
                if res.jira_migration_id.auto_export_work_log:
                    res.jira_migration_id.add_time_logs(res, time_log_ids)
                    res.last_export = datetime.datetime.now()
        except Exception as e:
            _logger.warning(e)
        return res

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
                'content': record.jira_raw_name,
                'is_header': record.is_header,
                'checked': record.checked,
                'sequence': record.sequence,
                'need_compile': True
            })
        return res

    def export_ticket_to_server(self, values={}):
        if values.get('mode', {}).get('worklog', False):
            self.export_time_log_to_jira()
        if values.get('mode', {}).get('ac', False):
            self.export_ac_to_jira()
