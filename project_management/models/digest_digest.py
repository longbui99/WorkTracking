from werkzeug.urls import url_join
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytz
from odoo import fields, models, _, api
from odoo.addons.project_management.utils.time_parsing import convert_second_to_time_format


def get_week_start(self):
    return -(int(self.env['res.lang']._lang_get(self.env.user.lang).week_start) % 7) + 1


def get_date_range(self, periodic):
    today = datetime.now()
    start_date, end_date = datetime.now(), datetime.now()
    if periodic == "daily":
        end_date = start_date - relativedelta(days=1)
    elif periodic == "weekly":
        week_start = get_week_start(self)
        base_date = today + relativedelta(days=week_start)
        start_date = base_date - relativedelta(days=base_date.weekday() + week_start)
        end_date = start_date + relativedelta(days=7)
    elif periodic == "monthly":
        end_date = end_date + relativedelta(months=1, day=1) - relativedelta(days=1)
        start_date = end_date - relativedelta(day=1)
    elif periodic == "quarterly":
        current_quarter = today.month // 3
        end_date = today + relativedelta(month=current_quarter * 3 + 1, day=1) - relativedelta(days=1)
        start_date = end_date - relativedelta(months=2, day=1)
    tz = pytz.timezone(self.env.user.tz or 'UTC')
    start_date = (start_date + relativedelta(hour=0, minute=0, second=0)).replace(tzinfo=tz).astimezone(pytz.utc)
    end_date = (end_date + relativedelta(hour=0, minute=0, second=0)).replace(tzinfo=tz).astimezone(pytz.utc)
    return start_date, end_date


class Digest(models.Model):
    _inherit = "digest.digest"

    jira_time_management = fields.Boolean('Management')

    def get_next_run_date(self):
        _, end_date = get_date_range(self, self.periodicity)
        return end_date

    @api.model
    def create(self, values):
        res = super().create(values)
        if 'periodicity' in values or 'jira_time_management' in values:
            res.next_run_date = res.get_next_run_date()
        return res

    def write(self, values):
        res = super().write(values)
        if 'periodicity' in values or 'jira_time_management' in values:
            self.next_run_date = self.get_next_run_date()
        return res

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
        start_date, end_date = get_date_range(self, self.periodicity)
        special_domain = self.get_logged_time_special_addition_domain()
        normal_domain = self.get_logged_time_normal_addition_domain()

        # Logged but haven't exported so far
        base_time_domain = [('user_id', '=', user_id.id),
                            ('start_date', '>=', start_date),
                            ('start_date', '<=', end_date)]
        log_ids = self.env["jira.time.log"].search(base_time_domain + special_domain)
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

    def _formatting_ticket_from_work_log(self, work_log_ids):
        return {}

    @api.model
    def _formatting_ticket_from_time_log(self, time_log_ids):
        res = {}
        for log in time_log_ids:
            if log.ticket_id not in res:
                res[log.ticket_id] = {
                    'ticket_key': log.ticket_id.ticket_key,
                    'ticket_name': log.ticket_id.ticket_name,
                    'log': [],
                    'total_duration': 0,
                    'time_duration': ''
                }
            res[log.ticket_id]['log'].append({
                'time': log.time,
                'description': log.description
            })
            res[log.ticket_id]['total_duration'] += log.duration
        for key in res:
            res[key]['time_duration'] = convert_second_to_time_format(res[key]['total_duration'])
        return res

    def _formatting_project(self, record):
        res = record.copy()
        res.update({
            "total_duration": 0,
            "payload": {}
        })
        payload = record["payload"]
        while len(payload) > 0:
            log = payload[0]
            if log.ticket_id.project_id.id not in res["payload"]:
                res["payload"][log.ticket_id.project_id.id] = {
                    "project_key": log.ticket_id.project_id.project_key,
                    "project_name": log.ticket_id.project_id.project_name,
                    "total_duration": 0,
                    'time_duration': ''
                }
                if res["payload"][log.ticket_id.project_id.id]:
                    log_ids = payload.filtered(lambda r: r.ticket_id.project_id == log.ticket_id.project_id)
                    payload -= log_ids
                    if payload._name == "jira.time.log":
                        res["payload"][log.ticket_id.project_id.id]["tickets"] = self._formatting_ticket_from_time_log(
                            log_ids)
                    elif payload._name == "jira.work.log":
                        res["payload"][log.ticket_id.project_id.id]["tickets"] = self._formatting_ticket_from_work_log(
                            log_ids)
                    record = res["payload"][log.ticket_id.project_id.id]
                    total_duration = sum(list([v['total_duration'] for v in record['tickets'].values()]))
                    record['total_duration'] = total_duration
                    record['time_duration'] = convert_second_to_time_format(total_duration)
                    res["total_duration"] += total_duration
        res["time_duration"] = convert_second_to_time_format(res["total_duration"])
        return res

    def _formatting_data(self, data):
        res = []
        for record in data:
            section = self._formatting_project(record)
            res.append(section)
        return res

    def _heading_data(self, formatted_data):
        res = {'total_duration': 0}
        for record in formatted_data:
            res['total_duration'] += record['total_duration']
        res['time_duration'] = convert_second_to_time_format(res['total_duration'])
        start_date, end_date = get_date_range(self, self.periodicity)
        res['tz'] = self.env.user.tz or 'UTC'
        res['start_date'] = start_date.astimezone(pytz.timezone(res['tz'])).strftime("%Y-%d-%m")
        res['end_date'] = end_date.astimezone(pytz.timezone(res['tz'])).strftime("%Y-%d-%m")
        res['name'] = self.name
        return res

    @api.model
    def mail_create_and_send(self):
        # Logged and exported
        for user_id in self.user_ids:
            data = self.get_user_data(user_id)
            formatted_data = self._formatting_data(data)
            heading_data = self._heading_data(formatted_data)
            content = self._generate_mail_content(user_id, user_id.company_id, formatted_data, heading_data)
            self.jira_send_main(user_id, user_id.company_id, content, formatted_data, heading_data)

    def _generate_mail_content(self, user, company, formatted_data, heading_data):
        web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        rendered_body = self.env['mail.render.mixin'].with_context(preserve_comments=True)._render_template(
            'project_management.project_management_digest_email',
            'jira.project',
            self.ids,
            engine='qweb_view',
            add_context={
                'content': formatted_data,
                'heading': heading_data,
                'web_base_url': web_base_url,
            },
            post_process=True
        )[self.id]
        full_mail = self.env['mail.render.mixin']._render_encapsulate(
            'project_management.project_management_digest_template',
            rendered_body,
            add_context={
                'company': company,
            },
        )
        mail_template = full_mail
        return mail_template

    def jira_send_main(self, user, company, content, formatted_data, heading_data):
        mail_values = {
            'subject': '%s: %s' % (heading_data['name'], heading_data['time_duration']),
            'email_from': company.partner_id.email_formatted,
            'email_to': user.partner_id.email,
            'body_html': content,
            'auto_delete': True,
        }
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send(raise_exception=False)
        return True