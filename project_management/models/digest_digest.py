from werkzeug.urls import url_join
from datetime import datetime
from odoo import fields, models, _, api
import pytz


def get_date_range(periodic):
    start_date, end_date = datetime.now(), datetime.now()

    return start_date, end_date


class Digest(models.Model):
    _inherit = "digest.digest"

    jira_time_management = fields.Boolean('Jira Time Management')

    def action_send(self):
        self.ensure_one()
        if not self.jira_time_management:
            return super(Digest, self).action_send()
        else:
            return self.mail_create_and_send()

    def get_logged_time_special_addition_domain(self):
        return []

    def get_logged_time_normal_addition_domain(self):
        return []

    def get_user_data(self, user_id):
        user_data = []
        start_date, end_date = get_date_range(self.periodic)
        special_domain = self.get_logged_time_special_addition_domain()
        normal_domain = self.get_logged_time_normal_addition_domain()

        # Logged but haven't exported so far
        base_time_domain = [('user_id', '=', user_id.id),
                            ('start_date', '>=', start_date),
                            ('start_date', '<=', end_date)]
        log_ids = self.env["jira.time.log"].search(base_time_domain + special_domain, order="Project")
        user_data.append({
            "title": "Done Work Logs",
            "payload": log_ids,
            "finalize": True
        })
        if len(special_domain):
            normal_log_ids = self.env["jira.time.log"].search(base_time_domain + normal_domain)
        else:
            normal_log_ids = self.env["jira.time.log"]

        if normal_log_ids:
            user_data.append({
                "title": "Haven't Done Work Logs",
                "payload": normal_log_ids,
                "finalize": False
            })
        return user_data

    def _formatting_ticket_from_work_log(self, work_log_ids, project_id):
        return {}

    def _formatting_ticket_from_time_log(self, time_log_ids, project_id):
        return {}

    def _formating_project(self, record):
        res = record.copy()
        res["payload"] = []
        for log in record["payload"]:
            if log.project_id not in record["payload"]:
                res["payload"][log.project_id] = {
                    "project_key": log.project_id.project_key,
                    "project_name": log.project_id.project_name,
                }
                if record["payload"]:
                    if record["payload"]._name == "jira.time.log":
                        res["payload"]["tickets"] = self._formatting_ticket_from_time_log(record["payload"],
                                                                                          record.project_id)
                    elif record["payload"]._name == "jira.work.log":
                        res["payload"]["tickets"] = self._formatting_ticket_from_work_log(record["payload"],
                                                                                          record.project_id)
        return res

    def _formating_data(self, data):
        res = []
        for record in data:
            section = self._formating_project(record)
            res.append(section)
        return res

    @api.model
    def mail_create_and_send(self):
        # Logged and exported
        user_ids = self.env["jira.project"].mapped('allowed_user_ids')
        company = self.env.user.company
        for user_id in user_ids:
            data = self.get_user_data(user_id)
            formatted_data = self._formating_data(data)
            content = self._generate_mail_content(formatted_data)
            self.jira_send_main(user_id, company, content)

    def _generate_mail_content(self, user, company, content, last_updated):
        web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        rendered_body = self.env['mail.render.mixin']._render_template(
            'novobi_dashboard_builder.bi_dashboard_digest_email',
            'bi.dashboard.item',
            self.ids,
            engine='qweb',
            add_context={
                'mail_content': content.get("mail_content"),
                'title': content.get('title'),
                'periodicity': content.get('periodicity'),
                'top_button_url': url_join(web_base_url, '/web/login'),
                'unsubscribe_id': self.id,
                'company': company.name,
                'sub_title': self.name,
                'last_updated': last_updated,
                'formatted_date': datetime.now().strftime('%b %d, %H:%M %p'),
            },
            post_process=True
        )[self.id]
        full_mail = self.env['mail.render.mixin']._render_encapsulate(
            'novobi_dashboard_builder.bi_dashboard_digest_layout',
            rendered_body,
            add_context={
                'company': company,
            },
        )
        mail_template = full_mail
        return mail_template

    def jira_send_main(self, user, company, content):
        start_date, end_date = get_date_range(self.periodic)
        user_tz = pytz.tzinfo(self.env.user.tz or 'UTC')
        mail_values = {
            'subject': '%s (%s - %s)' % (self.name, start_date.astimezone(user_tz), end_date.astimezone(user_tz)),
            'email_from': company.partner_id.email_formatted,
            'email_to': user.partner_id.email,
            'body_html': content,
            'auto_delete': True,
        }
        mail.send(raise_exception=False)
        return True
