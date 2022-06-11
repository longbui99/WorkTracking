# Copyright © 2021 Novobi, LLC
# See LICENSE file for full copyright and licensing details.

{
    'name': 'Jira Migration',
    'summary': 'Jira Migration',
    'category': 'Project',
    "author": "Drake Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['project_management', 'queue_job'],
    "data": [
        'data/queue_job_function.xml',
        'data/cron_job.xml',
        'security/ir.model.access.csv',

        'views/hr_employee_views.xml',
        'views/jira_migration_views.xml',
        'views/jira_ticket_views.xml',
        'views/jira_project_views.xml',

        'views/menus.xml',

        'wizard/load_by_link_views.xml',

    ],
    "application": False,
}
