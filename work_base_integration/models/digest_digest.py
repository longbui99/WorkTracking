from werkzeug.urls import url_join
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pytz
from odoo import fields, models, _, api


class Digest(models.Model):
    _inherit = "digest.digest"

    def get_logged_time_special_addition_domain(self):
        return [('id_onhost', '!=', False)]

    def get_logged_time_normal_addition_domain(self):
        return [('id_onhost', '=', False)]

    def get_user_data(self, user_id):
        user_data = []
        start_date, end_date = self.get_date_range(self, self.periodicity)
        return super().get_user_data(user_id)