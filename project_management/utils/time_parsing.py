from odoo.tools.float_utils import float_is_zero
from datetime import datetime
import pytz
from dateutil.relativedelta import relativedelta


def convert_second_to_time_format(time):
    data = [{'key': 'hours', 'duration': 3600},
            {'key': 'minutes', 'duration': 60},
            {'key': 'seconds', 'duration': 1}]
    response = ""
    for segment in data:
        duration = segment['duration']
        if time >= duration:
            response += f"{int(time / duration)} {segment['key']} "
            time -= (int(time / duration) * duration)
    return response


def convert_second_to_log_format(time):
    data = [{'key': 'w', 'duration': 604800},
            {'key': 'd', 'duration': 86400},
            {'key': 'h', 'duration': 3600},
            {'key': 'm', 'duration': 60},
            {'key': 's', 'duration': 1}]
    response = ""
    for segment in data:
        duration = segment['duration']
        if time >= duration:
            response += f"{int(time / duration)}{segment['key']} "
            time -= (int(time / duration) * duration)
    return response


def convert_log_format_to_second(log_data):
    logs = log_data.strip().split(' ')
    total_time = 0
    data = {'w': 604800, 'd': 86400, 'h': 3600, 'm': 60, 's': 1}
    for log in logs:
        if len(log) <= 1:
            raise AttributeError("Your format is incorrect")
        else:
            total_time += int(log[:-1]) * data.get(log[-1], 0)
    if float_is_zero(total_time, 3):
        raise AttributeError("Nothing to log")
    return total_time


def get_week_start(self):
    employee_id = self.env["hr.employee"].search([('user_id', '=', self.env.user.id)], limit=1)
    return (employee_id and (-int(employee_id.week_start%7) + 1) or 0)


def get_date_range(self, periodic):
    if periodic[-2:] == "ly":
        periodic = periodic[:-2]
    tz = pytz.timezone(self.env.user.tz or 'UTC')
    today = datetime.now()
    start_date, end_date = datetime.now(tz), datetime.now(tz)
    last = 0
    if periodic.startswith("last"):
        last = int(periodic[5])
        periodic = periodic[7:]
    if periodic in ['day', 'dai']:
        end_date += relativedelta(days=1-last)
        start_date = end_date - relativedelta(days=1 + last)
    elif periodic == "week":
        week_start = get_week_start(self)
        base_date = today + relativedelta(days=week_start)
        start_date = (base_date - relativedelta(days=base_date.weekday() + week_start + 7 * last)).replace(tzinfo=tz)
        end_date = start_date + relativedelta(days=7)
    elif periodic == "month":
        end_date = end_date + relativedelta(months=1 - last, day=1) - relativedelta(days=1)
        start_date = end_date - relativedelta(day=1)
    elif periodic == "quarter":
        current_quarter = today.month // 3
        end_date = today + relativedelta(month=(current_quarter - last) * 3 + 1, day=1) - relativedelta(days=1)
        start_date = end_date - relativedelta(months=2, day=1)
    start_date = (start_date + relativedelta(hour=0, minute=0, second=0)).astimezone(pytz.utc)
    end_date = (end_date + relativedelta(hour=0, minute=0, second=0)).astimezone(pytz.utc)
    return start_date, end_date
