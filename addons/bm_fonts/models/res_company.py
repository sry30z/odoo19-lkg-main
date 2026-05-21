# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    font = fields.Selection(
        selection_add=[
            ("NotoSansThai", "Noto Sans Thai"),
            ("Sarabun", "Sarabun"),
        ]
    )