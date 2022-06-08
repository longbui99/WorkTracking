from odoo.tools.float_utils import float_is_zero


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
