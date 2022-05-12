from odoo import api, fields, models, _


class LoadByLinkTransient(models.TransientModel):
    _name = 'jira.load.by.link'
    _description = 'JIRA Load By Link'

    type = fields.Selection([('ticket', 'Ticket'), ('project', 'Project')], string='Type', default='ticket')
    link_line_ids = fields.One2many('jira.load.by.link.line', 'origin_id', string="Keys")
    migration_id = fields.Many2one('jira.migration', string='Migration')

    def load(self):
        self.ensure_one()
        self.migration_id.load_by_keys(self.type, self.link_line_ids.mapped('url'))


class LoadByLinkLine(models.TransientModel):
    _name = 'jira.load.by.link.line'
    _description = "JIRA Load By Link Line"

    url = fields.Char(string="Key", required=True)
    origin_id = fields.Many2one('jira.load.by.link', string='Origin')
