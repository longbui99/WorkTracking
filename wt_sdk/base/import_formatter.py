
from abc import ABC, abstractmethod

def load_from_key_paths(self, object, paths):
    res = object
    for key in paths:
        if key in res and res.get(key) is not None:
            res = res[key]
        else:
            return None
    return res

class Issue(ABC):
    def __init__(self, data):
        self.summary = load_from_key_paths(issue_fields, self.map.summary)
        self.issue_key = issue['key']
        self.issue_url = self.map_url(issue['key'])
        self.hour_point = load_from_key_paths(issue_fields, self.map.estimate_hour) or 0.0
        self.fibonacy_point = load_from_key_paths(issue_fields, self.map.story_point)
        self.create_date = load_from_key_paths(issue_fields, self.map.created_date)
        self.project_key = load_from_key_paths(issue_fields, self.map.project)
        self.assignee_email = load_from_key_paths(issue_fields, self.map.assignee)
        self.status_key = load_from_key_paths(issue_fields, self.map.status)
        self.tester_email = load_from_key_paths(issue_fields, self.map.tester)
        self.issue_type_key = load_from_key_paths(issue_fields, self.map.issue_type)
        self.status_key = load_from_key_paths(issue_fields, self.map.new_status)
        if issue_fields.get('parent'):
            parent = issue_fields['parent']
            parent['project'] = issue_fields['project']
            self.epic = Issue(parent)
 
class ImportingIssue(ABC):
        
    @abstractmethod
    def load_batch_issues(self, issues):
        pass 

    @abstractmethod
    def load_single_issue(self, issue):
        pass 
    
    @abstractmethod
    def load_batch_work_logs(self, logs):
        pass 

    @abstractmethod
    def load_single_work_logs(self, log):
        pass

    