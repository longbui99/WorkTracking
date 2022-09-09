import yaml
from urllib.parse import urlparse
import logging
import json
from odoo.addons.wt_sdk.base.import_formatter import ImportingIssue

_logger = logging.getLogger(__name__)


def load_from_key_paths(o, paths):
    res = o
    for key in paths:
        if key in res and res.get(key) is not None:
            res = res[key]
        else:
            return None
    return res


class Checklist:
    def __init__(self, data):
        self.is_header = data['is_header']
        self.name = data['name']
        self.key = data.get('id' or self.string_to_int(name)
        self.sequence = data['rank']
        self.checked = data['checked']
    
    def string_to_int(s):
        ord3 = lambda x: '%.3d' % ord(x)
        return int(''.join(map(ord3, s)))

    def parsing(self):
        if self.server_type == "cloud":
            return self.cloud_parsing
        elif self.server_type == "self_hosting":
            return self.self_hosted_parsing
        else:
            raise TypeError("Doesn't support type: " + self.server_type)

    def self_hosted_exporting(self, ac_ids):
        return ac_ids.mapped(
            lambda r: {
                "name": r.wt_raw_name,
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
        if self.server_type == "cloud":
            return self.cloud_exporting
        elif self.server_type == "self_hosting":
            return self.self_hosted_exporting
        else:
            raise TypeError("Doesn't support type: " + self.server_type)

class Issue:
    def __init__(self, data, map):
        issue_fields = data['fields']
        self.summary = load_from_key_paths(issue_fields, map.summary)
        self.issue_key = data['key']
        self.issue_url = map.map_url(data['key'])
        self.hour_point = load_from_key_paths(issue_fields, map.estimate_hour) or 0.0
        self.fibonacci_point = load_from_key_paths(issue_fields, map.story_point)
        self.create_date = load_from_key_paths(issue_fields, map.created_date)
        self.project_key = load_from_key_paths(issue_fields, map.project)
        self.assignee_email = load_from_key_paths(issue_fields, map.assignee)
        self.assignee_name = load_from_key_paths(issue_fields, map.assignee_name)
        self.tester_email = load_from_key_paths(issue_fields, map.tester)
        self.tester_name = load_from_key_paths(issue_fields, map.tester_name)
        self.issue_type_key = load_from_key_paths(issue_fields, map.issue_type)
        self.raw_type = load_from_key_paths(issue_fields, map.new_issue_key)
        self.remote_status_id = load_from_key_paths(issue_fields, map.status_id)
        self.status_key = load_from_key_paths(issue_fields, map.status_key)
        self.raw_status_key = load_from_key_paths(issue_fields, map.new_status)
        self.remote_id = int(data['id'])
        raw_checklist = load_from_key_paths(issue_fields, map.checklist)
        if raw_checklist:
            self.checklists = map.map_checklists(raw_checklist)
        if issue_fields.get('parent'):
            parent = issue_fields['parent']
            parent['fields']['project'] = issue_fields['project']
            self.epic = Issue(parent, map)
        else:
            self.epic = None


class ImportJiraCloudIssue:

    def __init__(self, server_type, server_url):
        self.status_id = ['status', 'id']
        self.story_point = ['customfield_10041']
        self.estimate_hour = ['customfield_10052']
        self.assignee = ['assignee', 'emailAddress']
        self.assignee_name = ['assignee', 'displayName']
        self.tester = ['customfield_11101', 'name']
        self.tester_name = ['customfield_11101', 'displayName']
        self.project = ['project', 'key']
        self.issue_type = ['issuetype', 'id']
        self.summary = ['summary']
        self.acceptance_criteria = ['customfield_10034']
        self.created_date = ['created']
        self.new_status = ['status']
        self.status_key = ['status', 'statusCategory', 'key']
        self.new_issue_key = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        self.checklist = ['']

    def map_checklists(self, data):
        yaml_values = yaml.safe_load(data)['items']
        checklists = []
        for index, record in enumerate(yaml_values):
            record['name'] = ""
            if record['text'].startswith('---'):
                record['name'] = record['text'][3:]
                record['is_header'] = True
            else:
                record['name'] = record['text']
                record['is_header'] = False
            record['rank'] = index
            record['checked'] = False
            checklists.append(Checklist(record))
        return checklists


class ImportJiraSelfHostedIssue:

    def __init__(self, server_type, server_url):
        self.status_id = ['status', 'id']
        self.story_point = ['customfield_10008']
        self.estimate_hour = ['customfield_11102']
        self.assignee = ['assignee', 'name']
        self.assignee_name = ['assignee', 'displayName']
        self.tester = ['customfield_11101', 'name']
        self.tester_name = ['customfield_11101', 'displayName']
        self.project = ['project', 'key']
        self.issue_type = ['issuetype', 'id']
        self.summary = ['summary']
        self.acceptance_criteria = ['customfield_10206']
        self.created_date = ['created']
        self.new_status = ['status']
        self.status_key = ['status', 'statusCategory', 'key']
        self.new_issue_key = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        self.checklist = ['']

    def map_checklists(self, data):
        checklists = []
        for key, value in data.items():
            value['is_header'] = value['isHeader']
            checklists.append(Checklist(value))
        return checklists


class ImportingJiraIssue(ImportingIssue):

    def __init__(self, server_type, server_url):
        if server_type == "self_hosting":
            self.map = ImportJiraSelfHostedIssue(server_type, server_url)
        elif server_type == "cloud":
            self.map = ImportJiraCloudIssue(server_type, server_url)
        else:
            raise TypeError("Doesn't support type: " + server_type)

    def parse_issues(self, issues):
        response = []
        for issue in issues:
            if issue.get('fields'):
                res = self.parse_issue(issue)
                response.append(res)
        return response

    def parse_issue(self, issue):
        return Issue(issue, self.map)

# Work Log

class ImportingJiraSelfHostedWorkLog:
    def __init__(self, server_url, server_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_on_wt = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'name']
        self.issue_id = ['issueId']


class ImportingJiraCloudWorkLog:
    def __init__(self, server_url, server_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_on_wt = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'emailAddress']
        self.issue_id = ['issueId']


class Log:
    def __init__(self, fields, map):
        self.time = load_from_key_paths(fields, map.time)
        self.duration = load_from_key_paths(fields, map.duration)
        self.description = load_from_key_paths(fields, map.description)
        self.remote_id = int(load_from_key_paths(fields, map.id_on_wt))
        self.start_date = load_from_key_paths(fields, map.start_date)
        self.author = load_from_key_paths(fields, map.author)
        self.remote_issue_id = int(load_from_key_paths(fields, map.issue_id))


class ImportingJiraWorkLog:

    def __init__(self, server_type, server_url):
        if server_type == "self_hosting":
            self.map = ImportingJiraSelfHostedWorkLog(server_type, server_url)
        elif server_type == "cloud":
            self.map = ImportingJiraCloudWorkLog(server_type, server_url)
        else:
            raise TypeError("Doesn't support type: " + server_type)

    def parse_logs(self, logs):
        response = []
        for log in logs:
            res = self.parse_log(log)
            response.append(res)
        return response

    def parse_log(self, log):
        return Log(log, self.map)
