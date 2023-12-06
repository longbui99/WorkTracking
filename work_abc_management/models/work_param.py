from odoo import models, fields, api, _


class WorkParams(models.Model):
    _name = "work.param"
    _description = "Work Params"
    _rec_name = "model"

    key = fields.Char(string="Key", required=True)
    model = fields.Char(string="Model", required=True)
    kwargs = fields.Char(string="Kwargs", required=True)