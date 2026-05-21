# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from datetime import datetime, timedelta
from odoo import api, models, fields, _
from odoo.exceptions import UserError
import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    def js_remove_outstanding_partial(self, partial_id):
        partial = self.env['account.partial.reconcile'].browse(partial_id)
        move_id1 = partial.debit_move_id.move_id.id
        move_id2 = partial.credit_move_id.move_id.id

        res = super(AccountMove, self).js_remove_outstanding_partial(partial_id)

        update1 = self.env['account.move'].search([('tax_cash_basis_rec_id', '=', None), ('tax_cash_basis_origin_move_id', '=', move_id1)])
        if update1:
            update1.line_ids.write({
                'vat_summary_type': 'None'
            })
        update2 = self.env['account.move'].search([('tax_cash_basis_rec_id', '=', None), ('tax_cash_basis_origin_move_id', '=', move_id2)])
        if update2:
            update2.line_ids.write({
                'vat_summary_type': 'None'
            })

        return res