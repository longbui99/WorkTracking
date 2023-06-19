from datetime import datetime
from odoo import api, fields, models, _
from odoo.addons.wt_migration.utils.ac_parsing import unparsing


class WtACs(models.Model):
    _inherit = "wt.ac"

    wt_raw_name = fields.Char(string="Task Name")

    @api.model
    def create(self, values):
        if 'name' in values and 'wt_raw_name' not in values:
            values['wt_raw_name'] = unparsing(values['name'])
        return super().create(values)

    def write(self, values):
        if 'name' in values and 'wt_raw_name' not in values:
            values['wt_raw_name'] = unparsing(values['name'])
        return super().write(values)

    def update_ac(self, values):
        res_id = super().update_ac(values)
        issue_id = self.browse(res_id).issue_id
        if issue_id.exists():
            for index, ac in enumerate(issue_id.ac_ids):
                ac.sequence = index
                ac.float_sequence = 0

        return res_id


class WtACParsing(models.Model):
    _name = "wt.ac.parsing"
    _description = "Parser for AC"
    _order = "sequence, id desc"

    start_tag = fields.Char("Start Tag", required=True)
    end_tag = fields.Char("End Tag")
    parser = fields.Char("Parser")
