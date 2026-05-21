# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

{
    'name': 'Employee Signature',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'author': 'Bizmate',
    'category': 'Employees',
    'website': 'https://www.unboxsol.com',
    'live_test_url': 'https://bizmate18.unboxsol.com',
    'summary': "Keep Employee's Signature Image to Employee's Private Data.",
    'price': 0,
    'currency': 'USD',
    'support': 'bizmate@unboxsol.com',

    'depends': [
        'base',
        'hr',
    ],
    'data': [
        'views/hr_employee_views.xml',
    ],
    'auto_install': False,
    'images': ['static/description/images/banner.gif'],
}
