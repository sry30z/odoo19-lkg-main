# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

{
    'name': 'Thailand Tax Invoice/Receipt',
    'version': '18.0.1.0.1',
    'license': 'LGPL-3',
    'author': 'Bizmate',
    'category': 'Accounting/Payment/Report',
    'website': 'https://www.unboxsol.com',
    'live_test_url': 'https://bizmate18.unboxsol.com',
    'summary': "Thailand Tax Invoice/Receipt Report on Payment and Portal (Support only case 1-on-1 between Invoice and Payment)",
    'price': 0,
    'currency': 'USD',
    'support': 'bizmate@unboxsol.com',

    'depends': [
        'account',
        'l10n_th',
        'sale'
    ],
    'data': [
        'views/tax_invoice_receipt_report.xml',
        'views/mail_template_data.xml',
        'views/account_payment_view.xml',
        'views/account_portal_templates.xml'
    ],
    'auto_install': False,
    'images': ['static/description/images/banner.gif'],
}
