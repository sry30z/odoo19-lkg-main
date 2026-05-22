from odoo import fields, models, api, _
from odoo.exceptions import UserError

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    sub_amount = fields.Monetary(string='Sub Amount')
    adjust_wht = fields.Boolean('Adjust')
    is_wht = fields.Boolean('Withholding Tax', default=True)

    wht_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string='WHT Type')

    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal')
    
    wht_line_ids = fields.One2many('account.payment.register.wht.line', 'wizard_id', string='WHT Lines')
    wht_amount = fields.Monetary(string='Withholding Tax', compute='_compute_wht_amounts', store=True)
    after_wh_payment_amount = fields.Monetary(string='Net Paid', compute='_compute_wht_amounts', store=True)
    wht_warning = fields.Char(compute='_compute_wht_warning')

    @api.depends('sub_amount', 'is_wht', 'amount', 'currency_id')
    def _compute_wht_warning(self):
        for rec in self:
            active_ids = self._context.get('active_ids', [])
            warnings = []
            if len(active_ids) > 1 and rec.is_wht:
                warnings.append("Multiple bills: Please verify WHT allocation. / กรุณาตรวจสอบการคำนวณ WHT สำหรับหลายเอกสาร")
            
            # Check for partial payment
            if rec.is_wht and rec.sub_amount:
                full_wht_lines, _ = rec._get_wht_lines_for_ratio(1.0)
                full_wht = sum(l[2]['amount'] for l in full_wht_lines)
                full_net = rec.sub_amount - full_wht
                if full_net and abs(rec.amount - full_net) > 0.01:
                    warnings.append("Partial Payment: WHT has been scaled proportionally. / ชำระบางส่วน: ระบบลดหลั่นยอด WHT ตามสัดส่วนอัตโนมัติ")
                    
            if rec.currency_id and rec.currency_id != rec.company_id.currency_id:
                warnings.append("Multi-currency: Ensure WHT base is correct. / หลายสกุลเงิน: กรุณาตรวจสอบฐาน WHT")
                
            rec.wht_warning = "\n".join(warnings) if warnings else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids')
        active_model = self._context.get('active_model')
        if active_ids:
            if active_model == 'account.move.line':
                lines = self.env['account.move.line'].browse(active_ids).exists()
                invoices = lines.mapped('move_id')
            elif active_model == 'account.move':
                invoices = self.env['account.move'].browse(active_ids).exists()
            else:
                # Fallback to lines in standard wizard if active_model is missing
                invoices = self.env['account.move'].browse(active_ids).exists()
                if not invoices:
                    lines = self.env['account.move.line'].browse(active_ids).exists()
                    invoices = lines.mapped('move_id')

            res['sub_amount'] = res.get('amount', sum(invoices.mapped('amount_total')))
            
            wht_lines, wht_types = self._get_wht_lines_for_ratio(1.0)
            
            res['wht_line_ids'] = wht_lines
            if wht_lines:
                res['is_wht'] = True
                wht_total = sum(l[2]['amount'] for l in wht_lines)
                if 'amount' in res and wht_total > 0:
                    # BR-04: Adjust the initial amount to be the net paid
                    # Depending on wht_pay_type, the amount adjustment is different, handled in onchange
                    pass
            if wht_types:
                res['wht_type'] = wht_types[0]
            
            # Default wht_pay_type from invoices if consistent
            if invoices and all(hasattr(inv, 'wht_pay_type') for inv in invoices):
                pay_types = list(set(invoices.mapped('wht_pay_type')))
                if len(pay_types) == 1 and pay_types[0]:
                    res['wht_pay_type'] = pay_types[0]
        return res

    @api.depends('wht_line_ids.amount', 'is_wht', 'amount', 'wht_pay_type')
    def _compute_wht_amounts(self):
        for rec in self:
            if rec.is_wht:
                rec.wht_amount = sum(rec.wht_line_ids.mapped('amount'))
                if rec.wht_pay_type == 'gross_up_forever':
                    # Amount already includes what vendor should get, which is full amount
                    rec.after_wh_payment_amount = rec.amount
                elif rec.wht_pay_type == 'gross_up_once':
                    # Need to check total base
                    base_total = sum(rec.wht_line_ids.mapped('base_amount'))
                    # Net paid = Base - WHT. The wizard `amount` field is the vendor net payment.
                    rec.after_wh_payment_amount = rec.amount
                else:
                    # normal
                    rec.after_wh_payment_amount = rec.amount
            else:
                rec.wht_amount = 0.0
                rec.after_wh_payment_amount = rec.amount

    def _get_wht_lines_for_ratio(self, ratio=1.0):
        active_ids = self._context.get('active_ids')
        active_model = self._context.get('active_model')
        if not active_ids:
            return [], []
            
        if active_model == 'account.move.line':
            lines = self.env['account.move.line'].browse(active_ids).exists()
            invoices = lines.mapped('move_id')
        elif active_model == 'account.move':
            invoices = self.env['account.move'].browse(active_ids).exists()
        else:
            invoices = self.env['account.move'].browse(active_ids).exists()
            if not invoices:
                lines = self.env['account.move.line'].browse(active_ids).exists()
                invoices = lines.mapped('move_id')

        all_wht = self.env['account.wht'].search([('tax_application', '=', 'payment')])
        wht_by_tax_id = {w.sale_tax_id.id: w for w in all_wht if w.sale_tax_id}

        wht_lines = []
        wht_types = []

        for inv in invoices:
            for line in inv.invoice_line_ids:
                if 'wht_tax_ids' in line._fields and line.wht_tax_ids:
                    for wht in line.wht_tax_ids:
                        rate = wht.amount / 100.0
                        base_amount = line.price_subtotal * ratio
                        
                        if self.wht_pay_type == 'gross_up_forever':
                            if abs(1 - rate) < 1e-9:
                                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % wht.name)
                            base_amount = base_amount / (1 - rate)
                        elif self.wht_pay_type == 'gross_up_once':
                            base_amount = base_amount + (base_amount * rate)
                            
                        wht_amount = round(base_amount * rate, 2)
                        account = wht.account_id if inv.move_type == 'in_invoice' else wht.refund_account_id
                        wht_lines.append((0, 0, {
                            'account_id': account.id if account else False,
                            'wht_id': wht.id,
                            'name': wht.name,
                            'base_amount': base_amount,
                            'amount': wht_amount,
                        }))
                        if wht.wht_type:
                            wht_types.append(wht.wht_type)
                elif line.tax_ids:
                    for tax in line.tax_ids:
                        wht = wht_by_tax_id.get(tax.id)
                        if wht:
                            rate = wht.amount / 100.0
                            base_amount = line.price_subtotal * ratio
                            
                            if self.wht_pay_type == 'gross_up_forever':
                                if abs(1 - rate) < 1e-9:
                                    raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % wht.name)
                                base_amount = base_amount / (1 - rate)
                            elif self.wht_pay_type == 'gross_up_once':
                                base_amount = base_amount + (base_amount * rate)
                                
                            wht_amount = round(base_amount * rate, 2)
                            account = wht.account_id if inv.move_type == 'in_invoice' else wht.refund_account_id
                            wht_lines.append((0, 0, {
                                'account_id': account.id if account else False,
                                'wht_id': wht.id,
                                'name': wht.name,
                                'base_amount': base_amount,
                                'amount': wht_amount,
                            }))
                            if wht.wht_type:
                                wht_types.append(wht.wht_type)
                                
        return wht_lines, wht_types

    @api.onchange('wht_pay_type')
    def _onchange_wht_pay_type(self):
        if self.is_wht:
            wht_lines, _ = self._get_wht_lines_for_ratio(1.0)
            self.wht_line_ids = [(5, 0, 0)] + wht_lines
            
            # Recalculate default payment amount based on pay type
            wht_total = sum(l[2]['amount'] for l in wht_lines)
            if self.wht_pay_type == 'gross_up_forever':
                self.amount = self.sub_amount
            elif self.wht_pay_type == 'gross_up_once':
                # Base is original + WHT_exp. Net = Base - WHT. Net = original_sub_amount + (WHT_exp - WHT)
                # But typically vendors want their full net amount.
                base_total = sum(l[2]['base_amount'] for l in wht_lines)
                self.amount = base_total - wht_total
            else:
                self.amount = self.sub_amount - wht_total

    @api.onchange('amount')
    def _onchange_amount_scale_wht(self):
        if self.is_wht and self.sub_amount:
            full_wht_lines, _ = self._get_wht_lines_for_ratio(1.0)
            full_wht = sum(l[2]['amount'] for l in full_wht_lines)
            
            full_net = self.sub_amount
            if self.wht_pay_type == 'normal':
                full_net = self.sub_amount - full_wht
            elif self.wht_pay_type == 'gross_up_once':
                base_total = sum(l[2]['base_amount'] for l in full_wht_lines)
                full_net = base_total - full_wht
            
            if full_net and self.amount != full_net:
                ratio = self.amount / full_net
                ratio = min(1.0, max(0.0, ratio))
            else:
                ratio = 1.0
                
            scaled_lines, _ = self._get_wht_lines_for_ratio(ratio)
            self.wht_line_ids = [(5, 0, 0)] + scaled_lines



    def _create_payments(self):
        payments = super()._create_payments()
        # ส่งประเภท ภ.ง.ด. ไปบันทึกในรายการจ่ายเงิน
        # (WHT Certificate จะถูกสร้างโดย action_post ใน account.payment แทน)
        if self.is_wht and self.wht_amount > 0:
            for payment in payments:
                payment.wht_type = self.wht_type
        return payments

class AccountPaymentRegisterWhtLine(models.TransientModel):
    _name = 'account.payment.register.wht.line'
    _description = 'WHT Line for Payment Register'

    wizard_id = fields.Many2one('account.payment.register', string='Wizard')
    account_id = fields.Many2one('account.account', string='Account')
    wht_id = fields.Many2one('account.wht', string='WHT Config')
    name = fields.Char(string='Label')
    base_amount = fields.Monetary(string='Base Amount')
    amount = fields.Monetary(string='WHT Amount')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')

    @api.onchange('wht_id')
    def _onchange_wht_id(self):
        """เมื่อเลือก WHT ให้ดึงชื่อและ account มาใส่อัตโนมัติ"""
        if self.wht_id:
            self.name = self.wht_id.name
            # ดูว่าเป็นฝั่งไหนจาก wizard context
            wizard = self.wizard_id
            if wizard and hasattr(wizard, '_context'):
                active_model = wizard._context.get('active_model', '')
            # ถ้าจ่ายออก (vendor bill) ใช้ account_id, ถ้ารับเข้า (customer invoice) ใช้ refund_account_id
            # Default: ใช้ account_id เสมอ (ผู้ใช้สามารถเปลี่ยนได้)
            self.account_id = self.wht_id.account_id or self.wht_id.refund_account_id

    @api.onchange('base_amount', 'wht_id')
    def _onchange_base_amount(self):
        """คำนวณ WHT Amount อัตโนมัติเมื่อเปลี่ยน Base Amount"""
        if self.wht_id and self.base_amount:
            self.amount = round(self.base_amount * self.wht_id.amount / 100.0, 2)
