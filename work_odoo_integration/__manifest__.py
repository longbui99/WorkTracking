{
    'name': 'Odoo Timesheet Host',
    'summary': 'Odoo Timesheet Host',
    'category': 'Project',
    "author": "Long Bui",
    "website": "https://www.longbui.met/",
    "depends": ['work_base_integration'],
    "license": "LGPL-3",
    "data": [
        
        'views/work_base_integration_views.xml',

        'wizards/token_confirmation_views.xml',

    ],
    "application": False,
}
