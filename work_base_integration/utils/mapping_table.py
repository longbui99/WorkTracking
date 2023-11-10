from tabnanny import check
import yaml
from urllib.parse import urlparse



class TaskMapping:
    def __init__(self, host_url, host_service):
        self.status = ['status', 'id']
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
        self.work_status = ['status', 'statusCategory', 'key']
        self.new_task_key = ['issuetype']
        host_url = urlparse(host_url).netloc
        self.map_url = lambda r: f"https://{host_url}/browse/{r}"
        if host_service == "self_hosting":
            pass
        elif host_service == "cloud":
            self.assignee = ['assignee', 'emailAddress']
            self.estimate_hour = ['customfield_10052']
            self.story_point = ['customfield_10041']
            self.acceptance_criteria = ['customfield_10034']
        else:
            raise TypeError("Doesn't support type: " + host_service)


class WorkLogMapping:
    def __init__(self, host_url, host_service):
        self.time = ['timeSpent']
        self.duration = ['timeSpentSeconds']
        self.description = ['comment']
        self.id_onhost = ['id']
        self.start_date = ['started']
        self.author = ['updateAuthor', 'name']
        if host_service == "self_hosting":
            pass
        elif host_service == "cloud":
            self.author = ['updateAuthor', 'emailAddress']
        else:
            raise TypeError("Doesn't support type: " + host_service)


class ACMapping:
    def __init__(self, host_url, host_service):
        self.host_service = host_service
        self.host_url = host_url

    def cloud_parsing(self, values):
        yaml_values = yaml.safe_load(values)['items']
        for index, record in enumerate(yaml_values):
            record['name'] = ""
            if record['text'].startswith('---'):
                record['name'] = record['text'][3:]
                record['isHeader'] = True
            else:
                record['name'] = record['text']
                record['isHeader'] = False
            record['rank'] = index
        return yaml_values

    def self_hosted_parsing(self, values):
        return values

    def parsing(self):
        if self.host_service == "cloud":
            return self.cloud_parsing
        elif self.host_service == "self_hosting":
            return self.self_hosted_parsing
        else:
            raise TypeError("Doesn't support type: " + self.host_service)

    def self_hosted_exporting(self, ac_ids):
        return ac_ids.mapped(
            lambda r: {
                "name": r.work_raw_name,
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
        if self.host_service == "cloud":
            return self.cloud_exporting
        elif self.host_service == "self_hosting":
            return self.self_hosted_exporting
        else:
            raise TypeError("Doesn't support type: " + self.host_service)
