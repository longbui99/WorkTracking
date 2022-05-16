import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class JiraProject(models.Model):
    _inherit = "jira.ticket"

    jira_migration_id = fields.Many2one('jira.migration', string='Jira Migration')

class JiraStatus(models.Model):
    _inherit = "jira.status"

    jira_key = fields.Char(string='Jira Key')


class JiraTimeLog(models.Model):
    _inherit = "jira.time.log"

    id_on_jira = fields.Integer(string='ID on JIRA')
