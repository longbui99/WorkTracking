from datetime import datetime
from odoo import api, fields, models, _
from odoo.addons.jira_migration.utils.ac_parsing import unparsing


class JiraACs(models.Model):
    _inherit = "jira.ac"

    jira_raw_name = fields.Char(string="Jira Name")