# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"
    
    name = fields.Char(readonly=True, translate=True)