# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    private_signature = fields.Binary(string="Signature", groups="hr.group_hr_user")