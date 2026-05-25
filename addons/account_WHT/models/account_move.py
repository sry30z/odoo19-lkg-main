# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_line_ids = fields.One2many(
        'account.move.tax', 'move_id',
        string='Tax Lines',
        readonly=True,
        copy=True
    )
    # Removed state redefinition as it breaks core Odoo functionality


    wht_line_ids = fields.One2many(
        'account.move.wht',
        'move_id',
        string='WHT Lines',
        readonly=True
    )
    wht_bill_created = fields.Boolean()

    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal', tracking=True)

    # Note: Removed unsafe override of payment_state selection that forced
    # 'in_payment' to display as 'Paid'. This was hiding unreconciled payments
    # from bank reconciliation and producing incorrect aging reports.


    taxes_line_ids = fields.One2many('account.move.tax.lines', 'move_id')
    wht_certificate_count = fields.Integer(compute='_compute_wht_certificate_count')

    # SME-friendly display label for payment status.
    # This is a DISPLAY-ONLY computed field — it never overrides payment_state or any
    # accounting logic. Safe to use in views and reports without side-effects.
    payment_status_display_label = fields.Char(
        string='สถานะการชำระ',
        compute='_compute_payment_status_display_label',
        store=False,
        help='Human-readable payment status for display in bills and reports.',
    )

    def _compute_payment_status_display_label(self):
        _LABEL_MAP = {
            'not_paid':   'ยังไม่ชำระ',
            'in_payment': 'ชำระแล้ว',
            'paid':       'ชำระแล้ว',
            'partial':    'ชำระบางส่วน',
            'reversed':   'ยกเลิก/Reversed',
            'invoicing_legacy': 'Legacy',
        }
        for move in self:
            state = move.payment_state or 'not_paid'
            move.payment_status_display_label = _LABEL_MAP.get(state, state)

    def _compute_wht_certificate_count(self):
        for move in self:
            move.wht_certificate_count = self.env['account.wht.certificate'].search_count([
                ('move_ids', 'in', move.ids),
                ('state', '!=', 'cancel')
            ])

    def action_view_wht_certificates(self):
        """Smart button บน Bill เพื่อดู WHT Certificates ทั้งหมด"""
        self.ensure_one()
        return {
            "name": _("WHT Certificates"),
            "type": "ir.actions.act_window",
            "res_model": "account.wht.certificate",
            "view_mode": "list,form",
            "domain": [('move_ids', 'in', self.ids)],
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_move_ids": [(6, 0, self.ids)],
            },
        }

    wht_base_amount = fields.Monetary(string='WHT Base', compute='_compute_wht_totals', store=True)
    wht_amount = fields.Monetary(string='WHT Amount', compute='_compute_wht_totals', store=True)
    wht_net_total = fields.Monetary(string='Net Total', compute='_compute_wht_totals', store=True)
    amount_due = fields.Monetary(string='Amount Due', compute='_compute_wht_totals', store=True)

    # Legacy fields mapping (to avoid breaking views before update)
    amount_wht_base = fields.Monetary(related='wht_base_amount')
    amount_wht = fields.Monetary(related='wht_amount')
    amount_net_total = fields.Monetary(related='wht_net_total')



    @api.depends('invoice_line_ids.price_total', 'invoice_line_ids.wht_tax_ids', 'wht_pay_type')
    def _compute_wht_totals(self):
        """
        Compute WHT totals using the centralized Service Layer.
        
        This replaces the previous duplicate calculation logic with a single
        source of truth service, ensuring deterministic behavior.
        """
        for move in self:
            if move.move_type not in ['in_invoice', 'out_invoice', 'in_refund', 'out_refund']:
                # Reset for non-invoice moves
                move.wht_base_amount = 0.0
                move.wht_amount = 0.0
                move.wht_net_total = sum(move.invoice_line_ids.mapped('price_total'))
                move.amount_due = move.wht_net_total
                continue
            
            # Use the centralized WHT Calculation Service
            service = self.env['wht.calculation.service']
            try:
                invoice_wht = service.calculate_invoice_wht(move)
                
                total_amount = sum(move.invoice_line_ids.mapped('price_total'))
                
                move.wht_base_amount = invoice_wht['total']['base']
                move.wht_amount = invoice_wht['total']['wht']
                move.amount_due = total_amount
                
                if move.wht_pay_type in ['gross_up_forever', 'gross_up_once']:
                    move.wht_net_total = total_amount
                else:
                    move.wht_net_total = total_amount - invoice_wht['total']['wht']

            except Exception as e:
                _logger.error(
                    "[WHT CALC] ERROR: WHT calculation failed for move %s (ID: %d): %s",
                    move.name, move.id, str(e), exc_info=True
                )
                # Fallback to zero on error to prevent blocking
                move.wht_base_amount = 0.0
                move.wht_amount = 0.0
                move.wht_net_total = sum(move.invoice_line_ids.mapped('price_total'))
                move.amount_due = move.wht_net_total




    def create_wht_line(self, line):
        amount = 0
        if self.move_type in ["out_invoice", "in_refund"]:
            amount = line.debit
        elif self.move_type in ["in_invoice", "out_refund"]:
            amount = line.credit

        if amount:
            self.wht_line_ids.create({
                'name': 'Withholding Tax',
                'account_id': line.account_id.id,
                'amount': amount,
                'move_id': self.id

            })
    @api.model_create_multi
    def create(self, vals_list):
        moves = super(AccountMove, self).create(vals_list)
        for move in moves:
            if move.move_type in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']:
                move.with_context(skip_wht_recompute=True).on_change_tax_ids()
                move.with_context(skip_wht_recompute=True)._onchange_invoice_line_ids()
        return moves

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        if any(f in vals for f in ['invoice_line_ids', 'wht_pay_type', 'line_ids']):
            if not self.env.context.get('skip_wht_recompute'):
                for move in self:
                    if move.move_type in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']:
                        move.with_context(skip_wht_recompute=True).on_change_tax_ids()
                        move.with_context(skip_wht_recompute=True)._onchange_invoice_line_ids()
        return res


    # def _synchronize_business_models(self, changed_fields):
    #     ''' Ensure the consistency between:
    #     account.payment & account.move
    #     account.bank.statement.line & account.move
    #
    #     The idea is to call the method performing the synchronization of the business
    #     models regarding their related journal entries. To avoid cycling, the
    #     'skip_account_move_synchronization' key is used through the context.
    #
    #     :param changed_fields: A set containing all modified fields on account.move.
    #     '''
    #     if self._context.get('skip_account_move_synchronization'):
    #         return
    #     self_sudo = self.sudo()
    #     self_sudo.origin_payment_id._synchronize_balance_from_moves(changed_fields)
    #     self_sudo.statement_line_id._synchronize_from_moves(changed_fields)

    def action_post(self):
        wht_lines_custom = self.line_ids.filtered(lambda line: line.is_wht_line)
        for wht_line in wht_lines_custom:
            for wht_tax in wht_line.wht_tax_ids:
                if wht_tax.tax_application == 'invoice':
                    # Check if WHT tax line already exists to avoid duplicates
                    existing_tax_line = self.wht_line_ids.filtered(
                        lambda l: l.wht_tax_id.id == wht_tax.id
                    )
                    if not existing_tax_line:
                        self.create_wht_line(wht_line)
                    break

        res = super(AccountMove, self).action_post()

        # Removed automatic creation of WHT certificate during Bill post.
        # WHT certificates will be created only when Payment is posted.
        return res


    def button_cancel(self):
        res = super(AccountMove, self).button_cancel()
        for move in self:
            # If cancelling a bill, cancel its WHT certificates
            if move.move_type in ['in_invoice', 'out_invoice', 'in_refund', 'out_refund']:
                certs = self.env['account.wht.certificate'].search([
                    ('move_ids', 'in', move.ids),
                    ('state', '!=', 'cancel')
                ])
                for cert in certs:
                    cert.action_cancel()
            
            # If cancelling a payment move, cancel its WHT certificates
            if move.payment_id:
                certs = self.env['account.wht.certificate'].search([
                    ('payment_id', '=', move.payment_id.id),
                    ('state', '!=', 'cancel')
                ])
                for cert in certs:
                    cert.action_cancel()
        return res

    def append_entry(self, wht, tax_amount, line, line_ids, tax_line=None):
        """
        Generate WHT move lines using the centralized Service Layer.
        
        This replaces the duplicate calculation logic with the service layer,
        ensuring deterministic and consistent accounting entries.
        """
        # Determine base amount (line subtotal or tax amount)
        base_amount = tax_amount if tax_amount else line.price_subtotal
        
        # Use the centralized WHT Calculation Service
        service = self.env['wht.calculation.service']
        
        # Determine if this is tax-on-tax
        if wht.type_tax_use == 'tax' and tax_line and tax_line.id in wht.sale_tax_id.ids:
            calc_result = service.calculate_tax_on_tax_wht(
                base_amount,
                wht.amount,
                self.wht_pay_type
            )
        else:
            calc_result = service.calculate_wht(
                base_amount,
                wht.amount,
                self.wht_pay_type
            )
        
        wht_amount = calc_result['wht']
        wht_expense_amount = calc_result['gross_up']
        
        if wht_amount:
            # WHT Liability/Asset Line
            debit = wht_amount if self.move_type in ["out_invoice", "in_refund"] else 0.0
            credit = wht_amount if self.move_type in ["in_invoice", "out_refund"] else 0.0

            line_ids.append((0, 0, {
                'name': wht.name,
                'account_id': wht.account_id.id,
                'debit': debit,
                'credit': credit,
                'partner_id': self.partner_id.id,
                'display_type': 'product',
                'wht_tax_ids': [(6, 0, [wht.id])],
                'is_wht_line': True
            }))

            # WHT Expense/Income Line for Gross-Up
            if wht_expense_amount > 0:
                exp_account = wht.expense_account_id.id if self.move_type in ["in_invoice", "out_refund"] else wht.income_account_id.id
                if not exp_account:
                    exp_account = wht.account_id.id

                exp_debit = wht_expense_amount if self.move_type in ["in_invoice", "out_refund"] else 0.0
                exp_credit = wht_expense_amount if self.move_type in ["out_invoice", "in_refund"] else 0.0

                line_ids.append((0, 0, {
                    'name': f"{wht.name} (Gross-up Absorbed)",
                    'account_id': exp_account,
                    'debit': exp_debit,
                    'credit': exp_credit,
                    'partner_id': self.partner_id.id,
                    'display_type': 'product',
                    'is_wht_line': True
                }))

        return line_ids

    def generate_wht_move_lines(self, wht, line, line_ids):
        if wht.tax_application == 'invoice':
            tax_amount = 0
            if line.tax_ids:
                for tax_line in line.tax_ids:
                    tax_amount = line.price_subtotal * round(tax_line.amount / 100, 2)
                    return self.append_entry(wht, tax_amount, line, line_ids, tax_line=tax_line)
            else:
                return self.append_entry(wht, tax_amount, line, line_ids, tax_line=None)
        return line_ids

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids(self):
        invoice_line_ids = self.invoice_line_ids

        line_ids = []
        for line in invoice_line_ids:
            if line.wht_tax_ids:
                for wht in line.wht_tax_ids:
                    line_ids = self.generate_wht_move_lines(wht, line, line_ids)

        wht_delete_ops = [(2, wht.id) for wht in self.line_ids.filtered(lambda l: l.is_wht_line)]
        
        if line_ids or wht_delete_ops:
            self.line_ids = wht_delete_ops + line_ids
            self.invoice_line_ids = invoice_line_ids


        return {}

    def action_register_payment(self):
        ''' Open the account.payment.register wizard to pay the selected journal entries.
        :return: An action opening the account.payment.register wizard.
        '''
        res = super(AccountMove, self).action_register_payment()
        wht_lines = self.invoice_line_ids.filtered(
            lambda l: not l.display_type or l.display_type == 'product').wht_tax_ids.filtered(
            lambda s: s.tax_application == 'payment')
        if wht_lines:
            if 'context' not in res:
                res['context'] = {}
            res['context']['default_wht_ids'] = wht_lines.ids
        return res

    @api.onchange('invoice_line_ids', 'wht_pay_type')
    def on_change_tax_ids(self):
        self.taxes_line_ids = [(5, 0, 0)]
        data = []
        for line in self.invoice_line_ids:
            if line.wht_tax_ids:
                for rec in line.wht_tax_ids:
                    amount = 0
                    rate = rec.amount / 100.0
                    
                    if rec.type_tax_use != 'tax':
                        base = line.price_subtotal
                        if self.wht_pay_type == 'gross_up_forever':
                            if abs(1 - rate) < 1e-9:
                                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % rec.name)
                            base = base / (1 - rate)
                        elif self.wht_pay_type == 'gross_up_once':
                            base = base + (base * rate)
                        amount = round(base * rate, 2)
                    elif rec.type_tax_use == 'tax' and rec.sale_tax_id.id in line.tax_ids.ids:
                        if rec.sale_tax_id.price_include:
                            tax_rate = 1 + rec.sale_tax_id.amount / 100.0
                            amount_after_tax = round(line.price_subtotal / tax_rate, 2) if tax_rate else line.price_subtotal
                            tax_amount = line.price_subtotal - amount_after_tax
                        else:
                            tax_amount = round(line.price_subtotal * (rec.sale_tax_id.amount / 100.0), 2)
                        
                        base_tax = tax_amount
                        if self.wht_pay_type == 'gross_up_forever':
                            if abs(1 - rate) < 1e-9:
                                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % rec.name)
                            base_tax = base_tax / (1 - rate)
                        elif self.wht_pay_type == 'gross_up_once':
                            base_tax = base_tax + (base_tax * rate)
                        amount = round(base_tax * rate, 2)
                    
                    if amount:
                        data.append((0, 0, {
                            'name': rec.name,
                            'amount': amount,
                            'account_id': rec.account_id.id if self.move_type in ['in_invoice', 'out_refund'] else rec.refund_account_id.id,
                            'wht_tax_id': rec.id,
                            'move_id': self._origin.id or self.id,
                        }))
        if data:
            self.taxes_line_ids = data

    def js_assign_outstanding_line(self, line_id):
        """Called when accountant clicks 'Add' to match an outstanding payment to this bill.
        After reconciliation completes, trigger WHT certificate creation if the bill is now paid.
        NOTE: Certificate creation is now handled by payment.action_post() (payment-centric).
        """
        res = super(AccountMove, self).js_assign_outstanding_line(line_id)
        # Certificate creation moved to payment-centric - remove invoice-centric call
        return res

    @api.depends('line_ids.matched_debit_ids', 'line_ids.matched_credit_ids', 'line_ids.reconciled')
    def _compute_payment_state(self):
        super(AccountMove, self)._compute_payment_state()

    def _create_wht_certificate_if_needed(self):
        """
        WHT Certificate creation with smart grouping:
        - หา certificate ที่มีอยู่แล้วของ partner + WHT type + WHT pay type เดียวกัน
        - Add lines ลงใบ certificate ที่มีอยู่แล้ว
        - ถ้าไม่มี ให้สร้างใหม่

        ทำให้ flow ง่ายขึ้น: 1 certificate ต่อ partner ต่อประเภท WHT ต่อช่วงเวลา
        """
        _logger.info("[WHT CERT] START: Checking %d move(s) for WHT certificate creation", len(self))
        
        for move in self:
            _logger.info(
                "[WHT CERT] Check: Move=%s (ID: %d), Payment State=%s, Move Type=%s, Partner=%s (ID: %d)",
                move.name, move.id, move.payment_state, move.move_type, 
                move.partner_id.name if move.partner_id else 'N/A',
                move.partner_id.id if move.partner_id else 0
            )

            if move.payment_state not in ('paid', 'in_payment'):
                _logger.warning(
                    "[WHT CERT] SKIP: Move %s - payment state is %s (not paid/in_payment)",
                    move.name, move.payment_state
                )
                continue

            if move.move_type not in ('in_invoice', 'in_refund'):
                _logger.warning(
                    "[WHT CERT] SKIP: Move %s - move type is %s (not in_invoice/in_refund)",
                    move.name, move.move_type
                )
                continue

            wht_taxes = move.invoice_line_ids.mapped('wht_tax_ids').filtered(
                lambda t: getattr(t, 'tax_application', '') == 'payment'
            )
            if not wht_taxes:
                _logger.warning(
                    "[WHT CERT] SKIP: Move %s - no WHT taxes found with tax_application=payment",
                    move.name
                )
                continue

            # STABLE: Use _find_payment_for_bill() instead of unstable helper field search
            payment = self.env['account.payment']._find_payment_for_bill(move)

            if not payment:
                _logger.warning(
                    "[WHT CERT] SKIP: Move %s - no payment found via stable discovery",
                    move.name
                )
                continue

            _logger.info(
                "[WHT CERT] Found payment %s (ID: %d) for move %s - proceeding with WHT certificate",
                payment.name, payment.id, move.name
            )
            
            wht_type = payment.wht_type or 'pnd53'
            wht_pay_type = move.wht_pay_type
            
            # STEP 1: หา certificate ที่มีอยู่แล้ว (Open certificate ของ partner เดียวกัน)
            existing_cert = self.env['account.wht.certificate'].search([
                ('partner_id', '=', move.partner_id.id),
                ('wht_type', '=', wht_type),
                ('wht_pay_type', '=', wht_pay_type),
                ('state', '=', 'done'),
                ('company_id', '=', payment.company_id.id),
                ('custom_key', '!=', False),  # เฉพาะที่มี custom_key (auto-generated)
            ], limit=1, order='create_date desc')
            
            # STEP 2: คำนวณ WHT lines
            service = self.env['wht.calculation.service']
            payment_wht = service.calculate_payment_wht(payment, move)
            
            if not payment_wht['by_invoice']:
                continue
            
            cert_line_vals = []
            for invoice_wht in payment_wht['by_invoice']:
                if invoice_wht['invoice_id'] != move.id:
                    continue
                    
                for line_wht in invoice_wht['by_line']:
                    line = self.env['account.move.line'].browse(line_wht['line_id'])
                    wht_tax = self.env['account.wht'].browse(line_wht['wht_tax_id'])
                    
                    if not wht_tax.income_type_id:
                        income_type_id = False
                        income_type_code = ''
                        income_type_name = wht_tax.description or wht_tax.name or 'Service'
                    else:
                        income_type_id = wht_tax.income_type_id.id
                        income_type_code = wht_tax.income_type_id.code
                        income_type_name = wht_tax.income_type_id.name
                    
                    cert_line_vals.append((0, 0, {
                        'income_type_id': income_type_id,
                        'income_type_code': income_type_code,
                        'income_type_name': income_type_name,
                        'income_type_text': wht_tax.description or wht_tax.name or 'Service',
                        'name': wht_tax.name,
                        'base_amount': line_wht['base'],
                        'tax_amount': line_wht['wht'],
                        'invoice_move_id': move.id,
                        'wht_pay_type': move.wht_pay_type,
                    }))

            if not cert_line_vals:
                _logger.warning("[WHT CERT] SKIP: Move %s - no certificate line values generated", move.name)
                continue

            # STEP 3: Add lines ลง certificate ที่มีอยู่แล้ว
            if existing_cert:
                # เพิ่ม lines ลง certificate เดิม
                _logger.info(
                    "[WHT CERT] UPDATE: Adding lines to existing certificate %s (ID: %d) for move %s",
                    existing_cert.certificate_no, existing_cert.id, move.name
                )
                existing_cert.write({
                    'line_ids': [(4, 0, vals) for vals in cert_line_vals],
                    'move_ids': [(4, move.id)],  # เพิ่ม bill เข้าไปใน move_ids
                    'wht_reference': f"{existing_cert.wht_reference}, {move.name}",
                })
                _logger.info(
                    "[WHT CERT] SUCCESS: Added %d WHT lines to existing certificate %s",
                    len(cert_line_vals), existing_cert.certificate_no
                )
            else:
                # สร้าง certificate ใหม่
                _logger.info(
                    "[WHT CERT] CREATE: Creating new certificate for move %s (partner: %s, WHT type: %s)",
                    move.name, move.partner_id.name, wht_type
                )
                cert_key = f"{payment.id}_{move.id}_{wht_type}_{wht_pay_type}_{payment.company_id.id}"
                self.env.cr.execute(
                    "SELECT id FROM account_wht_certificate WHERE custom_key = %s FOR UPDATE",
                    (cert_key,)
                )

                check_duplicate = self.env['account.wht.certificate'].search([
                    ('custom_key', '=', cert_key),
                    ('state', '!=', 'cancel')
                ], limit=1)
                if check_duplicate:
                    _logger.warning(
                        "[WHT CERT] IDEMPOTENT SKIP: Certificate with custom_key already exists (move: %s)",
                        move.name
                    )
                    continue

                new_cert = self.env['account.wht.certificate'].create({
                    'partner_id': move.partner_id.id,
                    'move_ids': [(6, 0, move.ids)],
                    'wht_reference': move.name,
                    'payment_id': payment.id,
                    'currency_id': move.company_id.currency_id.id,
                    'wht_type': wht_type,
                    'wht_pay_type': wht_pay_type,
                    'issue_date': payment.date or fields.Date.context_today(self),
                    'pay_date': payment.date or fields.Date.context_today(self),
                    'line_ids': cert_line_vals,
                    'custom_key': cert_key,
                })
                new_cert._onchange_partner_id()
                if new_cert.partner_taxid and new_cert.line_ids:
                    _logger.info(
                        "[WHT CERT] CONFIRM: Confirming new certificate %s",
                        new_cert.certificate_no
                    )
                    new_cert.action_confirm()
                _logger.info(
                    "[WHT CERT] SUCCESS: Created new WHT certificate %s for move %s",
                    new_cert.certificate_no, move.name
                )
        
        _logger.info("[WHT CERT] END: Certificate creation flow completed for %d move(s)", len(self))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    wht_tax_ids = fields.Many2many(
        'account.wht', 
        string='WHT',
        compute='_compute_wht_tax_ids',
        store=True,
        readonly=False
    )
    wht_id = fields.Many2one('account.wht', string='WHT ID')
    wht_rate = fields.Float(string='WHT Rate', related='wht_id.amount', readonly=True)
    wht_amount = fields.Monetary(string='WHT Amount')
    wht_type = fields.Selection(related='wht_id.wht_type', string='WHT Type', readonly=True)

    is_wht_line = fields.Boolean()
    wht_invoice_ref_id = fields.Many2one('account.move')

    @api.depends('wht_id')
    def _compute_wht_tax_ids(self):
        for line in self:
            if line.wht_id:
                line.wht_tax_ids = [(6, 0, [line.wht_id.id])]
            else:
                line.wht_tax_ids = [(5, 0, 0)]

    @api.onchange('wht_id')
    def _onchange_wht_id(self):
        if self.wht_id:
            self.wht_tax_ids = [(6, 0, [self.wht_id.id])]
        else:
            self.wht_tax_ids = [(5, 0, 0)]