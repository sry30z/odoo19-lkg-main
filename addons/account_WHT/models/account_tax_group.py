# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    is_wht = fields.Boolean('WHT')
