from odoo import models, api, fields, _


class CloneRule(models.Model):
    _name = "work.clone.rule"
    _description = "Clone Between JIRA Rule"
    _order = "sequence, id desc"

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string="Name", required=True)
    src_host_id = fields.Many2one("work.base.integration", string="Source Server")
    dest_host_id = fields.Many2one("work.base.integration", string="Destination Server")

    clone_status_ids = fields.One2many('work.clone.status.rule', 'clone_rule_id', string="Status Rules")
    clone_type_ids = fields.One2many('work.clone.type.rule', 'clone_rule_id', string="Type Rules")
    clone_field_ids = fields.One2many('work.clone.field.rule', 'clone_rule_id', string="Field Rules")
    clone_project_ids = fields.One2many('work.clone.project.rule', 'clone_rule_id', string="Project Rules")
    default_project_id = fields.Many2one('work.project', string="Default Project", domain="[('host_id','=',dest_host_id)]")
    clone_epic_ids = fields.One2many('work.clone.epic.rule', 'clone_rule_id', string="Epic Rules")
    default_epic_id = fields.Many2one("work.task", string="Default Epic", domain="[('epic_ok','=',True),('host_id','=',dest_host_id)]")
    clone_priority_ids = fields.One2many('work.clone.priority.rule', 'clone_rule_id', string="Priority Rules")

class StatusRule(models.Model):
    _name = "work.clone.status.rule"
    _description = "Clone Status Rules"

    source_status_ids = fields.Many2many("work.status", "src_status_dest_status_rel", "status_rule_id", "status_id", string="Source Status")
    dest_status_id = fields.Many2one("work.status", string="Destination")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")

class TypeRule(models.Model):
    _name = "work.clone.type.rule"
    _description = "Clone Type Rules"

    src_type_ids = fields.Many2many("work.type", "src_type_dest_type_rel", "type_rule_id", "type_id", string="Source Type")
    dest_type_id = fields.Many2one("work.type", string="Destination")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")

class ProjectRule(models.Model):
    _name = "work.clone.project.rule"
    _description = "Clone Type Rules"

    src_project_ids = fields.Many2many("work.project", "src_type_dest_project_rel", "project_rule_id", "project_id", string="Source Project")
    dest_project_id = fields.Many2one("work.project", string="Destination")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")

class EpicRule(models.Model):
    _name = "work.clone.epic.rule"
    _description = "Clone Type Rules"

    src_epic_ids = fields.Many2many("work.task", "src_type_dest_epic_rel", "epic_rule_id", "epic_id", string="Source Epic", domain="[['epic_ok', '=', True]]")
    dest_epic_id = fields.Many2one("work.task", string="Destination", domain="[['epic_ok', '=', True]]")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")

class priorityRule(models.Model):
    _name = "work.clone.priority.rule"
    _description = "Clone Priority Rules"

    src_priority_ids = fields.Many2many("work.priority", "src_type_dest_priority_rel", "priority_rule_id", "priority_id", string="Source Priority")
    dest_priority_id = fields.Many2one("work.priority", string="Destination")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")

class FieldRules(models.Model):
    _name = "work.clone.field.rule"
    _inherit = ['mail.render.mixin']
    _description = "Clone Field Rules"

    field_id = fields.Many2one("ir.model.fields", string="Field", required=True, ondelete="cascade")
    template = fields.Html(string="Template", render_engine='qweb', translate=True, sanitize=False)
    keep_raw = fields.Boolean(string="Keep RAW")
    clone_rule_id = fields.Many2one("work.clone.rule", string="Clone Rule")