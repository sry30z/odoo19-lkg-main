# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    name = fields.Char(required=True, translate=True)