# -*- coding: utf-8 -*-
from odoo import fields, models, api, _


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

    # FORCE STATUS TO PAID: Override the selection or compute logic to eliminate 'in_payment'
    payment_state = fields.Selection(
        selection_add=[('in_payment', 'Paid')], # Map the label 'In Payment' to 'Paid' for display
    )


    taxes_line_ids = fields.One2many('account.move.tax.lines', 'move_id')

    wht_base_amount = fields.Monetary(string='WHT Base', compute='_compute_wht_totals', store=True)
    wht_amount = fields.Monetary(string='WHT Amount', compute='_compute_wht_totals', store=True)
    wht_net_total = fields.Monetary(string='Net Total', compute='_compute_wht_totals', store=True)
    amount_due = fields.Monetary(string='Amount Due', compute='_compute_wht_totals', store=True)

    # Legacy fields mapping (to avoid breaking views before update)
    amount_wht_base = fields.Monetary(related='wht_base_amount')
    amount_wht = fields.Monetary(related='wht_amount')
    amount_net_total = fields.Monetary(related='wht_net_total')



    @api.depends('invoice_line_ids.price_total', 'invoice_line_ids.price_subtotal', 'invoice_line_ids.wht_tax_ids', 'taxes_line_ids.amount', 'wht_pay_type')
    def _compute_wht_totals(self):
        for move in self:
            total_amount = sum(move.invoice_line_ids.mapped('price_total'))
            base_original = sum(move.invoice_line_ids.filtered(lambda l: l.wht_tax_ids).mapped('price_subtotal'))
            
            wht_base_total = 0.0
            wht_amount_total = 0.0
            
            for line in move.invoice_line_ids:
                if line.wht_tax_ids:
                    for rec in line.wht_tax_ids:
                        rate = rec.amount / 100.0
                        line_wht_amount = 0.0
                        if rec.type_tax_use != 'tax':
                            if move.wht_pay_type == 'gross_up_forever':
                                base = line.price_subtotal / (1 - rate)
                                line_wht_amount = round(base * rate, 2)
                                wht_base_total += base
                            elif move.wht_pay_type == 'gross_up_once':
                                base = line.price_subtotal + (line.price_subtotal * rate)
                                line_wht_amount = round(base * rate, 2)
                                wht_base_total += base
                            else:
                                line_wht_amount = round(line.price_subtotal * rate, 2)
                                wht_base_total += line.price_subtotal
                        else:
                            line_wht_amount = round(line.price_subtotal * rate, 2)
                            wht_base_total += line.price_subtotal
                        wht_amount_total += line_wht_amount
            
            wht_total_amount = sum(move.taxes_line_ids.mapped('amount')) or wht_amount_total
            
            move.wht_base_amount = wht_base_total
            move.wht_amount = wht_total_amount
            move.amount_due = total_amount
            
            if move.wht_pay_type in ['gross_up_forever', 'gross_up_once']:
                move.wht_net_total = total_amount
            else:
                move.wht_net_total = total_amount - wht_total_amount




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
        wht_amount = 0
        wht_expense_amount = 0
        rate = wht.amount / 100.0

        if wht.type_tax_use != 'tax':
            base = line.price_subtotal
            if self.wht_pay_type == 'gross_up_forever':
                base = base / (1 - rate)
                wht_amount = round(base * rate, 2)
                wht_expense_amount = wht_amount
            elif self.wht_pay_type == 'gross_up_once':
                wht_expense_amount = round(base * rate, 2)
                base = base + wht_expense_amount
                wht_amount = round(base * rate, 2)
            else:
                wht_amount = round(base * rate, 2)
                wht_expense_amount = 0
        elif tax_amount and tax_line and tax_line.id in wht.sale_tax_id.ids and wht.type_tax_use == 'tax':

            base = tax_amount
            if self.wht_pay_type == 'gross_up_forever':
                base = base / (1 - rate)
                wht_amount = round(base * rate, 2)
                wht_expense_amount = wht_amount
            elif self.wht_pay_type == 'gross_up_once':
                wht_expense_amount = round(base * rate, 2)
                base = base + wht_expense_amount
                wht_amount = round(base * rate, 2)
            else:
                wht_amount = round(base * rate, 2)
                wht_expense_amount = 0

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
        """
        res = super(AccountMove, self).js_assign_outstanding_line(line_id)
        for move in self:
            move._create_wht_certificate_if_needed()
        return res

    @api.depends('line_ids.matched_debit_ids', 'line_ids.matched_credit_ids', 'line_ids.reconciled')
    def _compute_payment_state(self):
        super(AccountMove, self)._compute_payment_state()

        for move in self:
            # Force 'paid' label if in_payment (display-only change, no DB write)
            if move.payment_state == 'in_payment':
                move.payment_state = 'paid'

    def _create_wht_certificate_if_needed(self):
        """Safe helper to create WHT Certificate when a bill becomes fully paid.
        Must be called from action hooks (js_assign_outstanding_line, action_post on Payment)
        and NOT from inside a compute field to avoid Odoo anti-pattern side-effects.
        """
        for move in self:
            if move.payment_state not in ('paid', 'in_payment'):
                continue
            if move.move_type not in ('in_invoice', 'in_refund'):
                continue

            # Only process bills with WHT taxes configured
            wht_taxes = move.invoice_line_ids.mapped('wht_tax_ids').filtered(
                lambda t: getattr(t, 'tax_application', '') == 'payment'
            )
            if not wht_taxes:
                continue

            # Guard against duplicates
            existing_cert = self.env['account.wht.certificate'].search([
                ('move_ids', 'in', move.ids)
            ], limit=1)
            if existing_cert:
                continue

            # Find linked payment
            payment = self.env['account.payment'].search([
                ('reconciled_bill_ids', 'in', move.ids)
            ], limit=1)

            # Build certificate lines
            cert_line_vals = []
            for line in move.invoice_line_ids:
                for wht in line.wht_tax_ids.filtered(lambda t: getattr(t, 'tax_application', '') == 'payment'):
                    rate = wht.amount / 100.0
                    l_base = line.price_subtotal

                    if move.wht_pay_type == 'gross_up_forever':
                        l_base = l_base / (1 - rate)
                    elif move.wht_pay_type == 'gross_up_once':
                        l_base = l_base + (l_base * rate)

                    l_tax = round(l_base * rate, 2)
                    cert_line_vals.append((0, 0, {
                        'income_type_id': wht.income_type_id.id if getattr(wht, 'income_type_id', False) else False,
                        'income_type_code': wht.income_type_id.code if getattr(wht, 'income_type_id', False) else '',
                        'income_type_name': wht.income_type_id.name if getattr(wht, 'income_type_id', False) else '',
                        'income_type_text': getattr(wht, 'description', '') or wht.name or 'Service',
                        'name': wht.name,
                        'base_amount': l_base,
                        'tax_amount': l_tax,
                        'invoice_move_id': move.id,
                        'wht_pay_type': move.wht_pay_type,
                    }))

            if cert_line_vals:
                new_cert = self.env['account.wht.certificate'].create({
                    'partner_id': move.partner_id.id,
                    'move_ids': [(6, 0, move.ids)],
                    'wht_reference': move.name,
                    'payment_id': payment.id if payment else False,
                    'currency_id': move.company_id.currency_id.id,
                    'wht_type': (payment.wht_type if payment else False) or 'pnd53',
                    'wht_pay_type': move.wht_pay_type,
                    'issue_date': (payment.date if payment else False) or fields.Date.context_today(self),
                    'pay_date': (payment.date if payment else False) or fields.Date.context_today(self),
                    'line_ids': cert_line_vals,
                })
                new_cert._onchange_partner_id()
                new_cert.action_confirm()


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