# Copyright © 2021 Novobi, LLC
# See LICENSE file for full copyright and licensing details.

{
    'name': 'Task Migration',
    'summary': 'Task Migration',
    'category': 'Project',
    "author": "Drake Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['project_management', 'queue_job'],
    "license": "LGPL-3",
    "data": [
        'data/queue_job_function.xml',
        'data/cron_job.xml',
        'data/ir_config_params.xml',
        'security/ir.model.access.csv',

        'views/hr_employee_views.xml',
        'views/wt_migration_views.xml',
        'views/wt_issue_views.xml',
        'views/wt_project_views.xml',

        'views/menus.xml',

        'wizard/load_by_link_views.xml',
        'wizard/export_by_pivot_time_views.xml',
        'wizard/token_confirmation.xml',

    ],
    "application": False,
    "post_init_hook": "post_init_hook",
}
