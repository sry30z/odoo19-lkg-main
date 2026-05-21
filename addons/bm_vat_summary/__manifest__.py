# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

{
    'name': 'VAT Summary Report',
    'version': '18.0.1.0.1',
    'license': 'LGPL-3',
    'author': 'Bizmate',
    'category': 'Accounting/Accounting',
    'website': 'https://www.unboxsol.com',
    'live_test_url': 'https://bizmate18.unboxsol.com',
    'summary': 'Summary VAT Transactions on System (Support to Tax Cash Basis both of "On Invoice" and "On Payment")',
    'price': 0,
    'currency': 'USD',
    'support': 'bizmate@unboxsol.com',

    'depends': [
        'account'
    ],
    'data': [
        'data/vat_summary_export.xml',
        'views/vat_summary_views.xml',
    ],
    'auto_install': False,
    'images': ['static/description/images/banner.gif'],
}
