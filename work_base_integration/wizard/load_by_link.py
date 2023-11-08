from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'work.load.by.link'
    _description = 'Task Load By Link'

    type = fields.Selection([('task', 'Task'), ('project', 'Project')], string='Type', default='task')
    link_line_ids = fields.One2many('work.load.by.link.line', 'origin_id', string="Keys")
    host_id = fields.Many2one('work.base.integration', string='Host')

    def load(self):
        self.ensure_one()
        res = dict()
        res[self.type] = self.link_line_ids.mapped('url')
        self.host_id._search_load(res, True)


class LoadByLinkLine(models.TransientModel):
    _name = 'work.load.by.link.line'
    _description = "Task Load By Link Line"

    url = fields.Char(string="Key", required=True)
    origin_id = fields.Many2one('work.load.by.link', string='Origin')
