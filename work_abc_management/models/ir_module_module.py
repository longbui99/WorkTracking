import ast
from odoo import models, fields, api

from odoo.addons.work_abc_management.utils.random_string import generate_random_string


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def action_launch_dependency(self):
        res = self.env['work.param'].sudo().create({
            'key': generate_random_string(10),
            'model': self._name,
            'kwargs': {
                "ids": self.ids
            }
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/planning/dependencies?key={res.key}",
        }

    def launch_flow(self, param):
        self = self.sudo()
        data_dict = ast.literal_eval(param.kwargs)
        module_ids = data_dict['ids']
        modules = self.browse(module_ids)
        datas = dict()
        for module in modules:
            res = {
                'datas': module.read()[0],
                'children': []
            }
            for child_module in (modules-module):
                if module in child_module.mapped('dependencies_id.depend_id'):
                    res['children'].append(str(child_module.id))
            datas[str(module.id)] = res
        return datas