# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

{
    'name': 'Font Noto Sans Thai and Sarabun',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'author': 'Bizmate',
    'category': 'Technical Settings',
    'website': 'https://www.unboxsol.com',
    'live_test_url': 'https://bizmate18.unboxsol.com',
    'summary': "Add Font Noto Sans Thai and Sarabun into System",
    'price': 0,
    'currency': 'USD',
    'support': 'bizmate@unboxsol.com',

    'depends': [
        'base'
    ],
    'assets': {
        'web.report_assets_common': [
            "bm_fonts/static/src/scss/font_custom.scss",
        ],
        'web.report_assets_pdf': [
            "bm_fonts/static/src/scss/font_custom.scss",
        ],
    },
    'data': [
        
    ],
    'auto_install': False,
    'images': ['static/description/images/banner.gif'],
}
