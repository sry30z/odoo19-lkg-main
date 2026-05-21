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


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    vat_summary_type = fields.Char(string="VAT Type", compute='_compute_vat_summary_type', store=True)
    vat_summary_name = fields.Char(string="Tax Invoice No.", compute='_compute_vat_summary_value', store=False)
    invoice_partner_display_name = fields.Char(string="Partner Name", compute='_compute_vat_summary_value', store=False)
    partner_vat = fields.Char(string="Partner VAT", compute='_compute_vat_summary_value', store=False)
    partner_ref = fields.Char(string="Partner Reference Doc No.", compute='_compute_vat_summary_value', store=False)
    all_tax_ids = fields.Many2many('account.tax', string="All Tax Name", compute='_compute_vat_summary_value', store=False)
    origin_doc_id = fields.Char(string="System Doc No.", compute='_compute_vat_summary_value', store=False)
    vat_amount = fields.Monetary(string="VAT Amount", compute='_compute_vat_summary_value', store=False)

    ex01_vat_summary_name = fields.Char(string="Tax Invoice No.", related='vat_summary_name', store=False)
    ex02_date = fields.Date(string="Tax Date", related='date', store=False)
    ex03_invoice_partner_display_name = fields.Char(string="Partner Name", related='invoice_partner_display_name', store=False)
    ex04_partner_vat = fields.Char(string="Partner VAT", related='partner_vat', store=False)
    ex05_partner_ref = fields.Char(string="Partner Reference Doc No.", related='partner_ref', store=False)
    ex06_tax_base_amount = fields.Monetary(string="Base Amount", related='tax_base_amount', store=False)
    ex07_vat_amount = fields.Monetary(string="VAT Amount", related='vat_amount', store=False)
    ex08_all_tax_ids = fields.Many2many('account.tax', string="Tax Name", related='all_tax_ids', store=False)
    ex09_origin_doc_id = fields.Char(string="System Doc No.", related='origin_doc_id', store=False)
    ex10_currency_id = fields.Many2one(string="Currency", related='currency_id', store=False)
    ex11_company_id = fields.Many2one(string="Company", related='company_id', store=False)

    @api.depends('move_id.state', 'move_id.payment_state')#, 'move_id.tax_cash_basis_rec_id', 'move_id.payment_reference')
    def _compute_vat_summary_type(self):
        for line in self:
            line.vat_summary_type = 'None'

            # Focus only Tax Lines
            if line.tax_base_amount > 0 and line.move_id.state == 'posted':
                source_move_id = False
                
                # Tax Cash Basis Move Line
                if line.move_id.tax_cash_basis_origin_move_id:
                    if line.move_id.tax_cash_basis_rec_id: # It is null when has reversal move
                        source_move_id = line.move_id.tax_cash_basis_origin_move_id
                # Customer Invoice / Vendor Bill
                elif not self.env['account.move'].search([('tax_cash_basis_origin_move_id', '=', line.move_id.id)]):
                    if line.tax_line_id.tax_exigibility == 'on_invoice':
                        source_move_id = line.move_id

                if source_move_id:
                    if source_move_id.is_outbound():
                        # Purchase VAT
                        line.vat_summary_type = 'Purchase'

                    elif source_move_id.is_inbound():
                        # Sales VAT
                        line.vat_summary_type = 'Sales'
            # Customer Invoice / Vendor Bill

    @api.depends('move_id.state', 'move_id.payment_state')
    def _compute_vat_summary_value(self):
        for line in self:
            line.vat_summary_name = ''
            line.invoice_partner_display_name = ''
            line.partner_vat = ''
            line.partner_ref = ''
            line.all_tax_ids = None
            line.origin_doc_id = None
            line.vat_amount = 0

            # Focus only Tax Lines
            if line.tax_base_amount > 0 and line.move_id.state == 'posted':
                tax_cash_basis_move = False
                source_move_id = False
                
                # Tax Cash Basis Move Line
                if line.move_id.tax_cash_basis_origin_move_id:
                    if line.move_id.tax_cash_basis_rec_id: # It is null when has reversal move
                        source_move_id = line.move_id.tax_cash_basis_origin_move_id
                        tax_cash_basis_move = line.move_id
                # Customer Invoice / Vendor Bill
                elif not self.env['account.move'].search([('tax_cash_basis_origin_move_id', '=', line.move_id.id)]):
                    source_move_id = line.move_id

                if source_move_id:
                    if source_move_id.is_outbound():
                        # Purchase VAT
                        line.invoice_partner_display_name = source_move_id.invoice_partner_display_name
                        line.partner_vat = source_move_id.partner_id.vat
                        line.partner_ref = source_move_id.ref
                        line.all_tax_ids = source_move_id.invoice_line_ids.filtered(lambda a: (a.tax_ids)).mapped('tax_ids')
                        line.origin_doc_id = source_move_id.name
                        line.vat_amount = line.debit

                        # Use Payment Reference
                        if tax_cash_basis_move:
                            line.vat_summary_name = source_move_id.payment_reference or '/'
                        # Use Bill Reference
                        else:
                            line.vat_summary_name = source_move_id.ref or '/'

                    elif source_move_id.is_inbound():
                        # Sales VAT
                        line.invoice_partner_display_name = source_move_id.invoice_partner_display_name
                        line.partner_vat = source_move_id.partner_id.vat
                        line.partner_ref = source_move_id.ref
                        line.all_tax_ids = source_move_id.invoice_line_ids.filtered(lambda a: (a.tax_ids)).mapped('tax_ids')
                        line.origin_doc_id = source_move_id.name
                        line.vat_amount = line.credit

                        # Use Receipt No.
                        if tax_cash_basis_move:
                            tax_cash_basis_rec = self.env['account.partial.reconcile'].search([('id', '=', tax_cash_basis_move.tax_cash_basis_rec_id.id)])
                            line.vat_summary_name = tax_cash_basis_rec.credit_move_id.move_name
                        # Use Invoice No.
                        else:
                            line.vat_summary_name = line.move_name
                else:
                    line.vat_summary_type = 'None'
            else:
                line.vat_summary_type = 'None'