# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

HR_WRITABLE_CUSTOM_FIELDS = [
    'private_signature',
]

class ResUsers(models.Model):
    _inherit = 'res.users'

    private_signature = fields.Binary(related='employee_id.private_signature', string="Signature", readonly=False, related_sudo=False)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + HR_WRITABLE_CUSTOM_FIELDS
    
    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + HR_WRITABLE_CUSTOM_FIELDS