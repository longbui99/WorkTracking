# Copyright © 2021 Novobi, LLC
# See LICENSE file for full copyright and licensing details.

{
    'name': 'Jira Migration',
    'summary': 'Jira Migration',
    'category': 'Project',
    "author": "Drake Bui",
    "website": "https://www.drakebui.ml/",
    "depends": ['project_management', 'hr'],
    "data": [
        'security/ir.model.access.csv',

        'views/hr_employee_views.xml',
        'views/jira_migration_views.xml',

        'views/menus.xml',

    ],
    "application": False,
}
