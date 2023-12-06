from odoo import models, api, fields, _
from odoo.exceptions import UserError

class LoadDateRange(models.Model):
    _name = "work.load.date.range"
    _description = "Load Date Range"

    start_date = fields.Datetime(string="From", default=fields.Datetime.now(), required=True)
    end_date = fields.Datetime(string="To", default=fields.Datetime.now(), readonly=True)
    host_ids = fields.Many2many("work.base.integration", string="Host", required=True)

    def action_load(self):
        self.ensure_one()
        start_date = self.start_date.timestamp() * 1000
        self.env['ir.config_parameter'].sudo().set_param('latest_unix', int(start_date))
        projects = self.env['work.project'].search([('host_id', 'in', self.host_ids.ids)])
        projects.with_context(default_group=f"{self._name},{self.id}").cron_fetch_task()
        queue_jobs = self.env['queue.job'].search([('group', '=', f"{self._name},{self.id}")])
        if len(queue_jobs):
            actions = self.env["ir.actions.act_window"]._for_xml_id("queue_job.action_queue_job")
            actions['domain'] = [('id', 'in', queue_jobs.ids)]
            return actions