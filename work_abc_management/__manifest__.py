# Copyright © 2021 Novobi, LLC
# See LICENSE file for full copyright and licensing details.

{ 
    'name': 'Project Management',
    'summary': 'Project Management',
    'category': 'Project',
    "author": "Drake Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['hr', 'digest'],
    "license": "LGPL-3",
    "data": [
        'data/mail_template.xml',
        'data/project_data.xml',
        'data/digest_email_template.xml',
        'data/system_data.xml',
        'data/cron_tasks.xml',

        'security/work_security.xml',
        'security/ir.model.access.csv',

        'views/work_agile_sprint_views.xml',
        'views/work_board_board_views.xml',
        'views/hr_employee_views.xml',
        'views/work_project_views.xml',
        'views/work_task_views.xml',
        'views/work_status_views.xml',
        'views/work_type_views.xml',
        'views/work_priority_views.xml',
        'views/work_time_logging_views.xml',
        'views/digest_email_views.xml',
        'views/work_billable_rule_views.xml',
        'views/work_task_template_views.xml',
        'views/work_budget_invoice_views.xml',
        'views/work_budget_views.xml',
        'views/work_finance_views.xml',
        'views/work_allocation_views.xml',

        'views/menus.xml',

        'wizard/work_logging_time_views.xml',
        'wizard/kick_off_counting_views.xml',
    ],
    "application": True,
    'assets': {
    }
}
