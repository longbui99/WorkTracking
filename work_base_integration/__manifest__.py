{
    'name': 'Work Integration',
    'summary': 'Work Integration',
    'category': 'Project',
    "author": "Long Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['work_abc_management', 'queue_job'],
    "license": "LGPL-3",
    "data": [
        'security/ir.model.access.csv',
        
        'data/queue_job_function.xml',
        'data/cron_job.xml',
        'data/ir_config_params.xml',

        'views/hr_employee_views.xml',
        'views/work_base_integration_views.xml',
        'views/work_task_views.xml',
        'views/work_time_log_views.xml',
        'views/work_project_views.xml',
        'views/work_field_map_views.xml',
        'views/clone_rule_views.xml',
        'views/work_priority_views.xml',
        'views/work_billable_rule_views.xml',

        'views/menus.xml',

        'wizard/load_by_link_views.xml',
        'wizard/export_by_pivot_time_views.xml',
        'wizard/token_confirmation.xml',
        'wizard/clone_to_host_views.xml',
        'wizard/fetch_task_views.xml',
        'wizard/load_date_range_views.xml',

    ],
    "application": False,
    "post_init_hook": "post_init_hook",
}
