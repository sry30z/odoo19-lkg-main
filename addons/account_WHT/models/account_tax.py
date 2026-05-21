# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_wht = fields.Boolean(string='Withholding Tax', default=False, help='Check if this tax is a Withholding Tax (WHT)')
    wht_type = fields.Selection([
        ('pnd3', 'P.N.D. 3'),
        ('pnd53', 'P.N.D. 53'),
    ], string='WHT Type', help='Type of Withholding Tax Certificate')

    def get_grouping_key(self, invoice_tax_val):
        """ Returns a string that will be used to group account.invoice.tax sharing the same properties"""
        self.ensure_one()
        return str(invoice_tax_val['tax_id']) + '-' + str(invoice_tax_val['account_id']) + '-' + str(
            invoice_tax_val['analytic_account_id'])
