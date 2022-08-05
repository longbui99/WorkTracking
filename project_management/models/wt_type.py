from odoo import api, fields, models, _


class JiraType(models.Model):
    _name = "wt.type"
    _description = "JIRA type"
    _order = 'write_date desc'
    
    name = fields.Char(string="Name", required=True)
    img = fields.Binary(string="Image", store=False)
    img_url = fields.Char(string="Image URL")
    img_base64 = fields.Char(string="Image Base64")
    key = fields.Char(string='Jira Key')