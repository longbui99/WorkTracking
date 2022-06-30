from odoo import models, api, fields, _


class Board(models.Model):
    _name = "board.board"
    _description = "Project Management Board"

    name = fields.Char(string="Name", required=1)
    project_id = fields.Many2one("jira.project", string="Project")
    type = fields.Selection([('kanban', 'Kanban'), ('scrum', 'Scrum')])
    sprint_ids = fields.One2many("agile.sprint", 'board_id', string="Sprints")

    def open_board_sprint(self):
        self.ensure_one()
        if self.project_id:
            active_sprint_id = self.sprint_ids.filtered(lambda sprint: sprint.state == 'active')
            action = self.project_id.action_open_sprint()
            action['name'] = self.name
            if active_sprint_id:
                action['domain'] += [('sprint_id', '=', active_sprint_id.id)]
                action['name'] += " - " + active_sprint_id.name
            return action
