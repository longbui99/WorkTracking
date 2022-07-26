from urllib.parse import urlparse


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
