{
    'name': 'Work Report',
    'summary': 'Work Report',
    'category': 'Project',
    "author": "Long Bui",
    "website": "https://www.longbui.net/",
    "depends": ['work_hierarchy', 'work_abc_management'],
    "license": "OPL-1",
    "data": [
        "views/allocation_busy_rate_reports.xml"
    ],
    "assets": {
        'web.assets_backend': [
            '/work_reporting/static/src/**/*.js',
        ],
    },
    "application": False,
}
