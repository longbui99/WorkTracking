from datetime import datetime
from odoo import api, fields, models, _
from odoo.addons.work_base_integration.utils.ac_parsing import unparsing


class WorkACs(models.Model):
    _inherit = "work.ac"

    work_raw_name = fields.Char(string="Task Name")

    @api.model
    def create(self, values):
        if 'name' in values and 'work_raw_name' not in values:
            values['work_raw_name'] = unparsing(values['name'])
        return super().create(values)

    def write(self, values):
        if 'name' in values and 'work_raw_name' not in values:
            values['work_raw_name'] = unparsing(values['name'])
        return super().write(values)

    def update_ac(self, values):
        res_id = super().update_ac(values)
        task_id = self.browse(res_id).task_id
        if task_id.exists():
            for index, ac in enumerate(task_id.ac_ids):
                ac.sequence = index
                ac.float_sequence = 0

        return res_id


class WorkACParsing(models.Model):
    _name = "work.ac.parsing"
    _description = "Parser for AC"
    _order = "sequence, id desc"

    start_tag = fields.Char("Start Tag", required=True)
    end_tag = fields.Char("End Tag")
    parser = fields.Char("Parser")
