from odoo import api, fields, models, _
from Crypto.Cipher import AES
import base64
import json


class JiraWorkLog(models.Model):
    _name = "wt.work.log"
    _description = "Task Work Log"
    _order = 'create_date desc'

    start = fields.Datetime(string='Start')
    end = fields.Datetime(string='End')
    duration = fields.Integer(string='Duration (s)', compute='_compute_duration', store=True)
    description = fields.Text(string='Description', required=True)
    ticket_id = fields.Many2one('wt.ticket', string='Ticket')
    cluster_id = fields.Many2one('wt.work.log.cluster', string='Cluster')
    state = fields.Selection([('progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Canceled')], string='Status',
                             default='progress')
    source = fields.Char(string='Source')
    user_id = fields.Many2one('res.users', string='User', required=True)
    encode_string = fields.Char(string="Hash String", compute='_compute_encode_string')

    @api.depends('start', 'end')
    def _compute_duration(self):
        for record in self:
            if record.start and record.end:
                record.duration = (record.end - record.start).total_seconds()

    def _compute_encode_string(self):
        cipher = AES.new(b'Bui Phi Long LML', AES.MODE_EAX)
        nonce = base64.decodebytes(cipher.nonce)
        one_time_link_env = self.env['one.time.link'].sudo()
        for record in self:
            ciphertext, tag = cipher.encrypt_and_digest(json.dumps({
                "record_id": record.id,
                "uid": record.user_id.id
            }))
            record.encode_string = base64.decodebytes(ciphertext)
            one_time_link_env.create({
                'key': record.encode_string,
                'value': nonce
            })


class JiraWorkLogCluster(models.Model):
    _name = "wt.work.log.cluster"
    _description = "Task Work Log Cluster"

    name = fields.Char(string='Cluster Name')
