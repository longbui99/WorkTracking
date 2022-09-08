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
        if issue_fields.get('parent'):
            parent = issue_fields['parent']
            parent['fields']['project'] = issue_fields['project']
            self.epic = Issue(parent, map)
        else:
            self.epic = None


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
        self.remote_id = load_from_key_paths(fields, map.id_on_wt)
        self.start_date = load_from_key_paths(fields, map.start_date)
        self.author = load_from_key_paths(fields, map.author)
        self.remote_issue_id = load_from_key_paths(fields, map.issue_id)


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
