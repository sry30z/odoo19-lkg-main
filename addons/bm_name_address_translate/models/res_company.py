# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class ResCompany(models.Model):
    _inherit = 'res.company'

    name = fields.Char(related='partner_id.name', string='Company Name', required=True, store=True, readonly=False, translate=True)
    street = fields.Char(compute='_compute_address', inverse='_inverse_street', translate=True)
    street2 = fields.Char(compute='_compute_address', inverse='_inverse_street2', translate=True)
    city = fields.Char(compute='_compute_address', inverse='_inverse_city', translate=True)