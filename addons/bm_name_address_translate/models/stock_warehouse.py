# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    def _default_name(self):
        count = self.env['stock.warehouse'].with_context(active_test=False).search_count([('company_id', '=', self.env.company.id)])
        return "%s - warehouse # %s" % (self.env.company.name, count + 1) if count else self.env.company.name
    
    name = fields.Char('Warehouse', required=True, default=_default_name, translate=True)