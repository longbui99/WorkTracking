from odoo.addons.queue_job.job import Job

from odoo import models, fields


class QueueJob(models.Model):
    _inherit = "queue.job"

    group = fields.Char(string="Queue Group")


def _store_values(self, create=False):
        vals = {
            "state": self.state,
            "priority": self.priority,
            "retry": self.retry,
            "max_retries": self.max_retries,
            "exc_name": self.exc_name,
            "exc_message": self.exc_message,
            "exc_info": self.exc_info,
            "company_id": self.company_id,
            "result": str(self.result) if self.result else False,
            "date_enqueued": False,
            "date_started": False,
            "date_done": False,
            "exec_time": False,
            "date_cancelled": False,
            "eta": False,
            "identity_key": False,
            "worker_pid": self.worker_pid,
            "graph_uuid": self.graph_uuid,
            "group": self.env.context.get("default_group")
        }

        if self.date_enqueued:
            vals["date_enqueued"] = self.date_enqueued
        if self.date_started:
            vals["date_started"] = self.date_started
        if self.date_done:
            vals["date_done"] = self.date_done
        if self.exec_time:
            vals["exec_time"] = self.exec_time
        if self.date_cancelled:
            vals["date_cancelled"] = self.date_cancelled
        if self.eta:
            vals["eta"] = self.eta
        if self.identity_key:
            vals["identity_key"] = self.identity_key

        dependencies = {
            "depends_on": [parent.uuid for parent in self.depends_on],
            "reverse_depends_on": [
                children.uuid for children in self.reverse_depends_on
            ],
        }
        vals["dependencies"] = dependencies

        if create:
            vals.update(
                {
                    "user_id": self.env.uid,
                    "channel": self.channel,
                    "uuid": self.uuid,
                    "name": self.description,
                    "func_string": self.func_string,
                    "date_created": self.date_created,
                    "model_name": self.recordset._name,
                    "method_name": self.method_name,
                    "job_function_id": self.job_config.job_function_id,
                    "channel_method_name": self.job_function_name,
                    "records": self.recordset,
                    "args": self.args,
                    "kwargs": self.kwargs,
                }
            )

        vals_from_model = self._store_values_from_model()
        # Sanitize values: make sure you cannot screw core values
        vals_from_model = {k: v for k, v in vals_from_model.items() if k not in vals}
        vals.update(vals_from_model)
        return vals

Job._store_values = _store_values