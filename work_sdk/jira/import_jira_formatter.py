import yaml
from urllib.parse import urlparse
import logging
import json
from odoo.addons.work_sdk.base.utils.md2json import md2json
from odoo.addons.work_sdk.base.import_formatter import ImportingTask

_logger = logging.getLogger(__name__)


def load_from_key_paths(o, paths):
    res = o
    try:
        for key in paths:
            if key in res and res.get(key) is not None:
                res = res[key]
            else:
                return None
    except:
        
        print(json.dumps(res, indent=4))
    return res


class Checklist:
    def __init__(self, data):
        self.is_header = data['is_header']
        self.name = data['name']
        self.key = data.get('id', self.string_to_float(data['name']))
        self.sequence = data['rank']
        self.checked = data['checked']

    def string_to_float(self, string):
        ord3 = lambda x: '%.3d' % ord(x)
        return float(''.join(map(ord3, string))[:15])

    def self_hosted_exporting(self, ac_ids):
        return ac_ids.mapped(
            lambda r: {
                "name": r.host_raw_name,
                "checked": r.checked,
                "rank": r.sequence,
                "isHeader": r.is_header,
                "id": int(r.key)
            }
        )

    def cloud_exporting(self, ac_ids):
        payloads = self.self_hosted_exporting(ac_ids=ac_ids)
        for payload in payloads:
            if payload['isHeader']:
                payload['name'] = '---' + payload['name']
        res = yaml.dump({"items": payloads}, sort_keys=False)
        return res

    def exporting(self):
        if self.host_type == "cloud":
            return self.cloud_exporting
        elif self.host_type == "self_hosting":
            return self.self_hosted_exporting
        else:
            raise TypeError("Doesn't support type: " + self.host_type)


class Task:
    def __init__(self, data, map):
        task_fields = data['fields']
        self.summary = load_from_key_paths(task_fields, map.summary)
        self.task_key = data['key']
        self.task_url = map.map_url(data['key'])
        self.hour_point = load_from_key_paths(task_fields, map.estimate_hour) or 0.0
        self.fibonacci_point = load_from_key_paths(task_fields, map.story_point)
        self.create_date = load_from_key_paths(task_fields, map.created_date)
        self.project_key = load_from_key_paths(task_fields, map.project)
        self.assignee_email = load_from_key_paths(task_fields, map.assignee)
        self.assignee_name = load_from_key_paths(task_fields, map.assignee_name)
        self.assignee_accountId = load_from_key_paths(task_fields, map.assignee_accountId)
        self.tester_email = load_from_key_paths(task_fields, map.tester)
        self.tester_name = load_from_key_paths(task_fields, map.tester_name)
        self.tester_accountId = load_from_key_paths(task_fields, map.tester_accountId)
        self.task_type_key = load_from_key_paths(task_fields, map.task_type)
        self.raw_type = load_from_key_paths(task_fields, map.new_task_type)
        self.remote_status_id = load_from_key_paths(task_fields, map.status_id)
        self.status_key = load_from_key_paths(task_fields, map.status_key)
        self.raw_status_key = load_from_key_paths(task_fields, map.new_status)
        self.remote_id = int(data['id'])
        self.raw_sprint = load_from_key_paths(task_fields, map.sprint)
        self.labels = load_from_key_paths(task_fields, map.labels)
        self.priority = load_from_key_paths(task_fields, map.priority)
        self.priority_key = load_from_key_paths(task_fields, map.priority_key)
        raw_checklist = load_from_key_paths(task_fields, map.checklist)
        self.depends = []
        for issue_dict in load_from_key_paths(task_fields, map.depend_key) or []:
            if 'inwardIssue' in issue_dict:
                self.depends.append(issue_dict['inwardIssue']['key'])
        if raw_checklist:
            self.checklists = map.map_checklists(raw_checklist)
        else:
            self.checklists = None
        if task_fields.get('parent'):
            parent = task_fields['parent']
            parent['fields']['project'] = task_fields['project']
            self.epic = Task(parent, map)
        else:
            self.epic = None


class ImportJiraCloudTask:

    def __init__(self, host_type, server_url, key_pair):
        self.status_id = [key_pair['task_status'], 'id']
        self.story_point = [key_pair['task_story_point']]
        self.estimate_hour = [key_pair['task_estimate_hour']]
        self.assignee = [key_pair['task_assignee'], 'emailAddress']
        self.assignee_name = [key_pair['task_assignee'], 'displayName']
        self.assignee_accountId = [key_pair['task_assignee'], 'accountId']
        self.tester = [key_pair['task_tester'], 'name']
        self.tester_name = [key_pair['task_tester'], 'displayName']
        self.tester_accountId = [key_pair['task_tester'], 'accountId']
        self.project = [key_pair['task_project'], 'key']
        self.task_type = [key_pair['task_type'], 'id']
        self.summary = [key_pair['task_summary']]
        self.acceptance_criteria = [key_pair['task_acceptance_criteria']]
        self.created_date = [key_pair['task_created_date']]
        self.new_status = [key_pair['task_status']]
        self.status_key = [key_pair['task_status'], 'statusCategory', 'key']
        self.new_task_type = [key_pair['task_type']]
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        self.checklist = [key_pair['checklist']]
        self.sprint = [key_pair['sprint']]
        self.labels = [key_pair['task_labels']]
        self.priority = [key_pair['priority']]
        self.priority_key = [key_pair['priority'], 'id']
        self.depend_key = [key_pair['depends']]

    def map_checklists(self, data):
        fields = md2json(data)
        checklists = fields.get('Default checklist', [])
        res = []
        for index, record in enumerate(checklists):
            record['rank'] = index
            record['checked'] = (record.get('status', False) == 'done')
            res.append(Checklist(record))
        return res


class ImportJiraSelfHostedTask:

    def __init__(self, host_type, server_url, key_pair):
        self.status_id = ['status', 'id']
        self.story_point = ['customfield_10008']
        self.estimate_hour = ['customfield_11102']
        self.assignee = ['assignee', 'name']
        self.assignee_name = ['assignee', 'displayName']
        self.tester = ['customfield_11101', 'name']
        self.tester_name = ['customfield_11101', 'displayName']
        self.project = ['project', 'key']
        self.task_type = ['issuetype', 'id']
        self.summary = ['summary']
        self.acceptance_criteria = ['customfield_10206']
        self.created_date = ['created']
        self.new_status = ['status']
        self.status_key = ['status', 'statusCategory', 'key']
        self.new_task_type = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        self.checklist = ['']
        self.sprint = ['customfield_10020']
        self.labels = ['labels']

    def map_checklists(self, data):
        checklists = []
        for key, value in data.items():
            value['is_header'] = value['isHeader']
            value['checked'] = (data.get('status', False) == 'done')
            checklists.append(Checklist(value))
        return checklists


class ImportingJiraTask(ImportingTask):

    def __init__(self, host_type, server_url, key_pair):
        if host_type == "self_hosting":
            self.map = ImportJiraSelfHostedTask(host_type, server_url, key_pair)
        elif host_type == "cloud":
            self.map = ImportJiraCloudTask(host_type, server_url, key_pair)
        else:
            raise TypeError("Doesn't support type: " + host_type)

    def parse_tasks(self, tasks):
        response = []
        for task in tasks:
            if task.get('fields'):
                res = self.parse_task(task)
                response.append(res)
        return response

    def parse_task(self, task):
        return Task(task, self.map)


# Work Log

class ImportingJiraSelfHostedWorkLog:
    def __init__(self, server_url, host_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_onhost = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'name']
        self.author_name = ['updateAuthor', 'displayName']
        self.task_id = ['issueId']
        self.create_date = ['created']
        self.write_date = ['updated']


class ImportingJiraCloudWorkLog:
    def __init__(self, server_url, host_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_onhost = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'emailAddress']
        self.author_name = ['updateAuthor', 'displayName']
        self.author_accountId = ['updateAuthor', 'accountId']
        self.task_id = ['issueId']
        self.create_date = ['created']
        self.write_date = ['updated']


class Log:
    def __init__(self, fields, map):
        self.time = load_from_key_paths(fields, map.time)
        self.duration = load_from_key_paths(fields, map.duration)
        self.description = load_from_key_paths(fields, map.description)
        self.remote_id = int(load_from_key_paths(fields, map.id_onhost))
        self.start_date = load_from_key_paths(fields, map.start_date)
        self.author = load_from_key_paths(fields, map.author)
        self.author_name = load_from_key_paths(fields, map.author_name)
        self.author_accountId = load_from_key_paths(fields, map.author_accountId)
        self.remote_task_id = int(load_from_key_paths(fields, map.task_id))
        self.create_date = load_from_key_paths(fields, map.create_date)
        self.write_date = load_from_key_paths(fields, map.write_date)


class ImportingJiraWorkLog:

    def __init__(self, host_type, server_url):
        if host_type == "self_hosting":
            self.map = ImportingJiraSelfHostedWorkLog(host_type, server_url)
        elif host_type == "cloud":
            self.map = ImportingJiraCloudWorkLog(host_type, server_url)
        else:
            raise TypeError("Doesn't support type: " + host_type)

    def parse_logs(self, logs):
        response = []
        for log in logs:
            res = self.parse_log(log)
            response.append(res)
        return response

    def parse_log(self, log):
        return Log(log, self.map)
