# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    name = fields.Char(string="Employee Name", related='resource_id.name', store=True, readonly=False, tracking=True, translate=True)
    private_street = fields.Char(string="Private Street", groups="hr.group_hr_user", translate=True)
    private_street2 = fields.Char(string="Private Street2", groups="hr.group_hr_user", translate=True)
    private_city = fields.Char(string="Private City", groups="hr.group_hr_user", translate=True)