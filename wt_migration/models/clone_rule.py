from odoo import models, api, fields, _


class CloneRule(models.Model):
    _name = "wt.clone.rule"
    _description = "Clone Between JIRA Rule"
    _order = "sequence, id desc"

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string="Name", required=True)
    src_migration_id = fields.Many2one("wt.migration", string="Source Server")
    dest_migration_id = fields.Many2one("wt.migration", string="Destination Server")

    clone_status_ids = fields.One2many('wt.clone.status.rule', 'clone_rule_id', string="Status Rules")
    clone_type_ids = fields.One2many('wt.clone.type.rule', 'clone_rule_id', string="Type Rules")
    clone_field_ids = fields.One2many('wt.clone.field.rule', 'clone_rule_id', string="Field Rules")
    clone_project_ids = fields.One2many('wt.clone.project.rule', 'clone_rule_id', string="Project Rules")
    clone_epic_ids = fields.One2many('wt.clone.epic.rule', 'clone_rule_id', string="Epic Rules")
    default_epic_id = fields.Many2one("wt.issue", string="Default Epic", domain="[('epic_ok','=',True)]")
    clone_priority_ids = fields.One2many('wt.clone.priority.rule', 'clone_rule_id', string="Priority Rules")

class StatusRule(models.Model):
    _name = "wt.clone.status.rule"
    _description = "Clone Status Rules"

    source_status_ids = fields.Many2many("wt.status", "src_status_dest_status_rel", "status_rule_id", "status_id", string="Source")
    dest_status_id = fields.Many2one("wt.status", string="Destination")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")

class TypeRule(models.Model):
    _name = "wt.clone.type.rule"
    _description = "Clone Type Rules"

    src_type_ids = fields.Many2many("wt.type", "src_type_dest_type_rel", "type_rule_id", "type_id", string="Source")
    dest_type_id = fields.Many2one("wt.type", string="Destination")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")

class ProjectRule(models.Model):
    _name = "wt.clone.project.rule"
    _description = "Clone Type Rules"

    src_project_ids = fields.Many2many("wt.project", "src_type_dest_project_rel", "project_rule_id", "project_id", string="Source")
    dest_project_id = fields.Many2one("wt.project", string="Destination")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")

class EpicRule(models.Model):
    _name = "wt.clone.epic.rule"
    _description = "Clone Type Rules"

    src_epic_ids = fields.Many2many("wt.issue", "src_type_dest_epic_rel", "epic_rule_id", "epic_id", string="Source", domain="[['epic_ok', '=', True]]")
    dest_epic_id = fields.Many2one("wt.issue", string="Destination", domain="[['epic_ok', '=', True]]")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")

class priorityRule(models.Model):
    _name = "wt.clone.priority.rule"
    _description = "Clone Priority Rules"

    src_priority_ids = fields.Many2many("wt.priority", "src_type_dest_priority_rel", "priority_rule_id", "priority_id", string="Source")
    dest_priority_id = fields.Many2one("wt.priority", string="Destination")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")

class FieldRules(models.Model):
    _name = "wt.clone.field.rule"
    _description = "Clone Field Rules"

    field_id = fields.Many2one("ir.model.fields", string="Field", required=True, ondelete="cascade")
    template = fields.Html(string="Template", render_engine='qweb', translate=True, sanitize=False)
    keep_raw = fields.Boolean(string="Keep RAW")
    clone_rule_id = fields.Many2one("wt.clone.rule", string="Clone Rule")