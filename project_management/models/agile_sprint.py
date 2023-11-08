from odoo import models, api, fields, _


class AgileSprint(models.Model):
    _name = "agile.sprint"
    _description = "Agile Sprint"
    _order = "state_sequence asc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Name", required=1)
    project_id = fields.Many2one("wt.project", string="Project", ondelete="cascade")
    board_id = fields.Many2one("board.board", string="Board")
    state = fields.Selection([('closed', 'Closed'), ('active', "In Progress"), ('future', "Future")], string="Status")
    issue_ids = fields.Many2many("wt.issue", string="Issues")
    company_id = fields.Many2one("res.company", related="project_id.company_id", store=True)
    state_sequence = fields.Integer(string="State Sequence", compute="_compute_state_sequence", compute_sudo=True, store=True)
    active = fields.Boolean(string="Active", default=True)

    def name_get(self):
        state_name = dict(self._fields['state'].selection)
        result = []
        for record in self:
            result.append((record.id, "%s - %s"%(record.name, state_name.get(record.state) or 'Unknow' )))
        return result
    
    def _compute_state_sequence(self):
        for record in self:
            state = 0
            if record.state == "closed":
                state = 3
            elif record.state == "active":
                state = 1
            elif record.state == "future":
                state = 2
            record.state_sequence = state
