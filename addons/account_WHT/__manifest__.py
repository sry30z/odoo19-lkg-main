# -*- coding: utf-8 -*-
{
    'name': "Withholding Tax",

    'summary': """
        This module will allow you to deduct WHT at the time of payment or Inovice/Bill. """,

    'description': """
        This module will allow you to deduct WHT at the time of payment.
    """,

    "author": "One Stop Odoo",
    "website": "https://onestopodoo.com/",
    "maintainer": "One Stop Odoo",
    'license': 'OPL-1',
    'category': 'Accounting',
    'version': '1.5',
    'depends': ['account', 'sale', 'purchase', 'web', 'bm_tax_invoice_receipt'],
    'data': [
        'data/wht_data.xml',
        'data/ir_sequence_data.xml',
        'data/wht_income_type_data.xml',
        'security/account_wht_security.xml',
        'security/ir.model.access.csv',
        'views/account_wht.xml',
        'views/account_move.xml',
'views/res_company_views.xml',
        'views/res_company_report_theme_views.xml',
        'views/account_payment.xml',
        'views/account_payment_register.xml',
        'views/account_tax.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
        'wizard/wht_bill_wizard.xml',
        'wizard/wht_export_wizard_views.xml',
        'reports/report_paperformats.xml',
        'reports/report_signature_block.xml',
        'reports/report_common_styles.xml',
        'reports/tax_invoice_report_templates.xml',
        'reports/tax_invoice_report_action.xml',
        'reports/sale_order_report_templates.xml',
        'reports/purchase_order_report_templates.xml',
        'reports/wht_50tawi_report.xml',
        'reports/report_payment_receipt_action.xml',
        'reports/report_payment_receipt_templates.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'account_WHT/static/src/css/report_common.css',
        ],
    },
}
