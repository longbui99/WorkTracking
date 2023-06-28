from odoo import api, fields, models, _


class WtType(models.Model):
    _name = "wt.type"
    _description = "Task type"
    _order = 'write_date desc'
    
    name = fields.Char(string="Name", required=True)
    img = fields.Binary(string="Image", store=False)
    img_url = fields.Char(string="Image URL")
    img_base64 = fields.Char(string="Image Base64")
    key = fields.Char(string='Task Key')
    default_personal = fields.Boolean(string="Personal default")
    company_id = fields.Many2one('res.company', string='Company', required=True)
    epic_ok = fields.Boolean(string="Epic?", default=False)
    active = fields.Boolean(string="Active", default=True)