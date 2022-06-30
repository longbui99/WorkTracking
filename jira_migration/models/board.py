from odoo import models, api, fields, _


class Board(models.Model):
    _inherit = "board.board"

    id_on_jira = fields.Integer(string="ID on JIRA")