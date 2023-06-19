from abc import ABC, abstractmethod


class ImportingIssue(ABC):

    @abstractmethod
    def parse_issues(self, issues):
        pass

    @abstractmethod
    def parse_issue(self, issue):
        pass
