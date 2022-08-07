from odoo import models, api, fields, _


class AgileSprint(models.Model):
    _name = "agile.sprint"
    _description = "Agile Sprint"

    name = fields.Char(string="Name", required=1)
    project_id = fields.Many2one("wt.project", string="Project")
    board_id = fields.Many2one("board.board", string="Board")
    state = fields.Selection([('closed', 'Closed'), ('active', "In Progress"), ('future', "Future")], string="Status")
    ticket_ids = fields.Many2many("wt.issue", string="Issues")
