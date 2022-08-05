from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'wt.load.by.link'
    _description = 'Tasks Load By Link'

    type = fields.Selection([('ticket', 'Ticket'), ('project', 'Project')], string='Type', default='ticket')
    link_line_ids = fields.One2many('wt.load.by.link.line', 'origin_id', string="Keys")
    migration_id = fields.Many2one('wt.migration', string='Migration')

    def load(self):
        self.ensure_one()
        res = dict()
        res[self.type] = self.link_line_ids.mapped('url')
        self.migration_id._search_load(res, True)


class LoadByLinkLine(models.TransientModel):
    _name = 'wt.load.by.link.line'
    _description = "Tasks Load By Link Line"

    url = fields.Char(string="Key", required=True)
    origin_id = fields.Many2one('wt.load.by.link', string='Origin')
