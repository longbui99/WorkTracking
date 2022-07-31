import yaml
from urllib.parse import urlparse

def string_to_int(s):
    ord3 = lambda x : '%.3d' % ord(x)
    return int(''.join(map(ord3, s)))

class IssueMapping:
    def __init__(self, server_url, server_type):
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
        self.jira_status = ['status', 'statusCategory', 'key']
        self.new_issue_key = ['issuetype']
        server_url = urlparse(server_url).netloc
        self.map_url = lambda r: f"https://{server_url}/browse/{r}"
        if server_type == "self_hosting":
            pass
        elif server_type == "cloud":
            self.assignee = ['assignee', 'emailAddress']
            self.estimate_hour = ['customfield_10052']
            self.story_point = ['customfield_10041']
        else:
            raise TypeError("Doesn't support type: " + server_type)


class WorkLogMapping:
    def __init__(self, server_url, server_type):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_on_jira = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'name']
        if server_type == "self_hosting":
            pass
        elif server_type == "cloud":
            self.author = ['updateAuthor', 'emailAddress']
        else:
            raise TypeError("Doesn't support type: " + server_type)


class ACMapping:
    def __init__(self, server_url, server_type):
        self.server_type = server_type
        self.server_url = server_url

    def cloud_parsing(self, values):
        yaml_values = yaml.safe_load(values)
        for index, record in enumerate(yaml_values['items']):
            record['name'] = "" 
            if record['text'].startswith('---'):
                record['name'] = record['text'][3:]
                record['isHeader'] = True
            else:
                record['name'] = record['text']
            record['id'] = string_to_int(record['name'])
            record['rank'] = index
        return yaml_values

    def self_hosted_parsing(self, values):
        return values

    def parsing(self):
        if self.server_type == "cloud":
            return self.cloud_parsing
        elif self.server_type == "self_hosting":
            return self.self_hosted_parsing 
        else:
            raise TypeError("Doesn't support type: " + self.server_type)