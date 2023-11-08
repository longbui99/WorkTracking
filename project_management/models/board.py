from odoo import models, api, fields, _


class Board(models.Model):
    _name = "board.board"
    _description = "Project Management Board"
    _order = 'is_favorite desc, id desc'

    name = fields.Char(string="Name", required=1)
    project_id = fields.Many2one("wt.project", string="Project", ondelete="cascade")
    type = fields.Selection([('kanban', 'Kanban'), ('scrum', 'Scrum'), ('simple', 'Simple')])
    sprint_ids = fields.One2many("agile.sprint", 'board_id', string="Sprints")
    is_favorite = fields.Boolean("Favorite")
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True)
    active = fields.Boolean(string="Active", default=True)

    def open_board_sprint(self):
        self.ensure_one()
        if self.project_id:
            active_sprint_ids = self.sprint_ids.filtered(lambda sprint: sprint.state == 'active')
            action = self.project_id.action_open_sprint()
            action['name'] = self.name
            if active_sprint_ids:
                action['domain'] += [('sprint_id', 'in', active_sprint_ids.ids)]
                action['name'] += " - %s"%(",".join(active_sprint_ids.mapped('display_name'))) 
            return action
