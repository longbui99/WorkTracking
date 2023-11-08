from odoo import api, fields, models, _
import requests

class ProjectGeneral(models.Model):
    _name = "project.general"
    _description = "Project General"

    def wake_up_server(self):
        server_urls = self.env["ir.config_parameter"].get_param("wake_up_server_list", False)
        if server_urls:
            server_urls = server_urls.split("\n")
            for url in server_urls:
                try:
                    requests.get(url.strip()+"/wakeup")
                except:
                    continue
