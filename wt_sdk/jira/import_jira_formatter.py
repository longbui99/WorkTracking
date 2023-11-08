import yaml
from urllib.parse import urlparse
import logging
import json
from odoo.addons.wt_sdk.base.utils.md2json import md2json
from odoo.addons.wt_sdk.base.import_formatter import ImportingIssue

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
        self.assignee_accountId = load_from_key_paths(issue_fields, map.assignee_accountId)
        self.tester_email = load_from_key_paths(issue_fields, map.tester)
        self.tester_name = load_from_key_paths(issue_fields, map.tester_name)
        self.tester_accountId = load_from_key_paths(issue_fields, map.tester_accountId)
        self.issue_type_key = load_from_key_paths(issue_fields, map.issue_type)
        self.raw_type = load_from_key_paths(issue_fields, map.new_issue_type)
        self.remote_status_id = load_from_key_paths(issue_fields, map.status_id)
        self.status_key = load_from_key_paths(issue_fields, map.status_key)
        self.raw_status_key = load_from_key_paths(issue_fields, map.new_status)
        self.remote_id = int(data['id'])
        self.raw_sprint = load_from_key_paths(issue_fields, map.sprint)
        self.labels = load_from_key_paths(issue_fields, map.labels)
        self.priority = load_from_key_paths(issue_fields, map.priority)
        self.priority_key = load_from_key_paths(issue_fields, map.priority_key)
        raw_checklist = load_from_key_paths(issue_fields, map.checklist)
        if raw_checklist:
            self.checklists = map.map_checklists(raw_checklist)
        else:
            self.checklists = None
        if issue_fields.get('parent'):
            parent = issue_fields['parent']
            parent['fields']['project'] = issue_fields['project']
            self.epic = Issue(parent, map)
        else:
            self.epic = None


class ImportJiraCloudIssue:

    def __init__(self, server_type, server_url, key_pair):
        self.status_id = [key_pair['issue_status'], 'id']
        self.story_point = [key_pair['issue_story_point']]
        self.estimate_hour = [key_pair['issue_estimate_hour']]
        self.assignee = [key_pair['issue_assignee'], 'emailAddress']
        self.assignee_name = [key_pair['issue_assignee'], 'displayName']
        self.assignee_accountId = [key_pair['issue_assignee'], 'accountId']
        self.tester = [key_pair['issue_tester'], 'name']
        self.tester_name = [key_pair['issue_tester'], 'displayName']
        self.tester_accountId = [key_pair['issue_tester'], 'accountId']
        self.project = [key_pair['issue_project'], 'key']
        self.issue_type = [key_pair['issue_type'], 'id']
        self.summary = [key_pair['issue_summary']]
        self.acceptance_criteria = [key_pair['issue_acceptance_criteria']]
        self.created_date = [key_pair['issue_created_date']]
        self.new_status = [key_pair['issue_status']]
        self.status_key = [key_pair['issue_status'], 'statusCategory', 'key']
        self.new_issue_type = [key_pair['issue_type']]
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        self.checklist = [key_pair['checklist']]
        self.sprint = [key_pair['sprint']]
        self.labels = [key_pair['issue_labels']]
        self.priority = [key_pair['priority']]
        self.priority_key = [key_pair['priority'], 'id']

    def map_checklists(self, data):
        fields = md2json(data)
        checklists = fields.get('Default checklist', [])
        res = []
        for index, record in enumerate(checklists):
            record['rank'] = index
            record['checked'] = (record.get('status', False) == 'done')
            res.append(Checklist(record))
        return res


class ImportJiraSelfHostedIssue:

    def __init__(self, server_type, server_url, key_pair):
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
        self.new_issue_type = ['issuetype']
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


class ImportingJiraIssue(ImportingIssue):

    def __init__(self, server_type, server_url, key_pair):
        if server_type == "self_hosting":
            self.map = ImportJiraSelfHostedIssue(server_type, server_url, key_pair)
        elif server_type == "cloud":
            self.map = ImportJiraCloudIssue(server_type, server_url, key_pair)
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
        self.author_name = ['updateAuthor', 'displayName']
        self.issue_id = ['issueId']
        self.create_date = ['created']
        self.write_date = ['updated']


class ImportingJiraCloudWorkLog:
    def __init__(self, server_url, server_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_on_wt = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'emailAddress']
        self.author_name = ['updateAuthor', 'displayName']
        self.author_accountId = ['updateAuthor', 'accountId']
        self.issue_id = ['issueId']
        self.create_date = ['created']
        self.write_date = ['updated']


class Log:
    def __init__(self, fields, map):
        self.time = load_from_key_paths(fields, map.time)
        self.duration = load_from_key_paths(fields, map.duration)
        self.description = load_from_key_paths(fields, map.description)
        self.remote_id = int(load_from_key_paths(fields, map.id_on_wt))
        self.start_date = load_from_key_paths(fields, map.start_date)
        self.author = load_from_key_paths(fields, map.author)
        self.author_name = load_from_key_paths(fields, map.author_name)
        self.author_accountId = load_from_key_paths(fields, map.author_accountId)
        self.remote_issue_id = int(load_from_key_paths(fields, map.issue_id))
        self.create_date = load_from_key_paths(fields, map.create_date)
        self.write_date = load_from_key_paths(fields, map.write_date)


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
