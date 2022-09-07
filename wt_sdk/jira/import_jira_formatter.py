from tabnanny import check
import yaml
from urllib.parse import urlparse
import logging
import json
from odoo.wt_sdk.base.import_base import ImportingIssue, Issue


_logger = logging.getLogger(__name__)

class ImportJiraCloudIssue:

    def __init__(self):
        self.status = ['status', 'id']
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
        self.wt_status = ['status', 'statusCategory', 'key']
        self.new_issue_key = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"

class ImportJiraSelfHostedIssue:

    def __init__(self):
        self.status = ['status', 'id']
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
        self.wt_status = ['status', 'statusCategory', 'key']
        self.new_issue_key = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"


class ImportingJiraIssue(ImportingIssue):
    
    def __init__(self, server_type, server_url, source):
        self.source = source
        if server_type == "self_hosting":
            self.map = ImportJiraSelfHostedIssue()
        elif server_type == "cloud":
            self.map = ImportJiraCloudIssue()
        else:
            raise TypeError("Doesn't support type: " + server_type)
    
    def parse_issues(self, issues):
        response = []
        for issue in issues:
            res = self.parse_issue(issue)
            response.append(res)
        return response

    def parse_issue(self, issue):
        return Issue(issue)
    
    def load_batch_work_logs(self, logs):
        pass 

    def load_single_work_logs(self, log):
        pass
