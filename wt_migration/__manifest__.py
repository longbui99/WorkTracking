{
    'name': 'Task Migration',
    'summary': 'Task Migration',
    'category': 'Project',
    "author": "Drake Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['project_management', 'queue_job'],
    "license": "LGPL-3",
    "data": [
        'security/ir.model.access.csv',
        
        'data/queue_job_function.xml',
        'data/cron_job.xml',
        'data/ir_config_params.xml',

        'views/hr_employee_views.xml',
        'views/wt_migration_views.xml',
        'views/wt_issue_views.xml',
        'views/wt_time_log_views.xml',
        'views/wt_project_views.xml',
        'views/wt_field_map_views.xml',
        'views/clone_rule_views.xml',
        'views/wt_priority_views.xml',
        'views/wt_billable_rule_views.xml',

        'views/menus.xml',

        'wizard/load_by_link_views.xml',
        'wizard/export_by_pivot_time_views.xml',
        'wizard/token_confirmation.xml',
        'wizard/clone_to_migration_views.xml',

    ],
    "application": False,
    "post_init_hook": "post_init_hook",
}
