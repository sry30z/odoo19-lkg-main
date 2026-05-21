# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class ResUsers(models.Model):
    _inherit = 'res.users'

    name = fields.Char(related='partner_id.name', inherited=True, readonly=False, translate=True)
    private_street = fields.Char(related='employee_id.private_street', string="Private Street", readonly=False, related_sudo=False, translate=True)
    private_street2 = fields.Char(related='employee_id.private_street2', string="Private Street2", readonly=False, related_sudo=False, translate=True)
    private_city = fields.Char(related='employee_id.private_city', string="Private City", readonly=False, related_sudo=False, translate=True)