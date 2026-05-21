# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo import models, fields, _
from odoo.exceptions import UserError

import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_non_vat = fields.Boolean(string="Is Non VAT?", compute='_compute_tax')
    is_service_invoice = fields.Boolean(string="Is Service Invoice?", compute='_compute_tax')
    is_tax_mix = fields.Boolean(string="Is Tax Mix? (Product + Service)", compute='_compute_is_tax_mix')

    matched_payment_compute_ids = fields.Many2many('account.payment', string='Matched Compute Payments', compute='_compute_matched_payment_compute_ids', store=False)
    
    def _compute_matched_payment_compute_ids(self):
        for move in self:
            payment_type = 'outbound' if move.is_outbound() else 'inbound'
            payments = self.env['account.payment'].search([('partner_id', 'parent_of', move.partner_id.id),
                                                           ('payment_type', '=', payment_type),
                                                           ('state', 'in', ('','in_process','paid'))])
            
            if payments:
                payment_ids = []
                for pay in payments:
                    if move.is_inbound() and len(pay.reconciled_invoice_ids.filtered(lambda m: m.id == move.id)) > 0:
                        payment_ids.append(pay.id)
                    elif move.is_outbound() and len(pay.reconciled_bill_ids.filtered(lambda m: m.id == move.id)) > 0:
                        payment_ids.append(pay.id)
                
                if len(payment_ids) > 0:
                    move.matched_payment_compute_ids = payment_ids
                else:
                    move.matched_payment_compute_ids = False
            else:
                move.matched_payment_compute_ids = False

    def _get_name_invoice_report(self):
        self.ensure_one()
        return 'bm_tax_invoice_receipt.report_invoice_document'

    def _compute_tax(self):
        for move in self:
            non_vat = True
            service_invoice = False
            for invoice_line in move.invoice_line_ids:
                if invoice_line.tax_ids:
                    if non_vat:
                        non_vat = False
                    for tax_id in invoice_line.tax_ids:
                        if tax_id.tax_exigibility == 'on_payment':
                            service_invoice = True
                            break
                if service_invoice:
                    break

            for invoice_line in move.invoice_line_ids:
                if invoice_line.tax_ids:
                    non_vat = False
                    break

            move.is_non_vat = non_vat 
            move.is_service_invoice = service_invoice 

    def _compute_is_tax_mix(self):
        for move in self:
            product_invoice = False
            service_invoice = False
            for invoice_line in move.invoice_line_ids:
                if invoice_line.tax_ids:
                    for tax_id in invoice_line.tax_ids:
                        if tax_id.tax_exigibility == 'on_payment':
                            service_invoice = True
                        else:
                            product_invoice = True
            move.is_tax_mix = product_invoice and service_invoice

    def action_post(self):
        for move in self:
            if move.is_tax_mix:
                raise UserError(_("Please do not mix tax (product and service)."))
            
        return super(AccountMove, self).action_post()
    
    def get_portal_payment_url(self, payment_id, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        self.ensure_one()
        url = '/my/invoice-payment/%s/%s' % (self.id, payment_id) + '%s?access_token=%s%s%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            '&report_type=%s' % report_type if report_type else '',
            '&download=true' if download else '',
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url

