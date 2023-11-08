from abc import ABC, abstractmethod


class ImportingTask(ABC):

    @abstractmethod
    def parse_tasks(self, tasks):
        pass

    @abstractmethod
    def parse_task(self, task):
        pass
