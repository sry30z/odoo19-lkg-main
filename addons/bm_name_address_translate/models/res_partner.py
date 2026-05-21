# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    name = fields.Char(index=True, default_export_compatible=True, translate=True)
    street = fields.Char(translate=True)
    street2 = fields.Char(translate=True)
    city = fields.Char(translate=True)