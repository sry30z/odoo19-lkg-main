# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

{
    'name': 'Setup System for Thailand',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'author': 'Bizmate',
    'category': 'Accounting/Localization/Master Data',
    'website': 'https://www.unboxsol.com',
    'live_test_url': 'https://bizmate18.unboxsol.com',
    'summary': "Load 'l10n_th' Chart of Account, Activate Thai language and Update province name in Thai",
    'price': 0,
    'currency': 'USD',
    'support': 'bizmate@unboxsol.com',

    'depends': [
        'base',
        'account',
        'l10n_th',
        'bm_name_address_translate',
    ],
    'data': [
    ],
    'pre_init_hook': 'check_partner_country',
    'post_init_hook': 'activate_th_language',
    'auto_install': False,
    'images': ['static/description/images/banner.gif'],
}
