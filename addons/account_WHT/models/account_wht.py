from odoo import fields, models, api, tools, _
from odoo.exceptions import UserError
from .wht_calculation_service import WHTCalculationService
import base64
import os
import logging
from odoo.modules.module import get_module_resource

_logger = logging.getLogger(__name__)

class WhtIncomeType(models.Model):
    _name = 'wht.income.type'
    _description = 'WHT Income Type Master Data'
    _order = 'sequence, code'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    certificate_line_ids = fields.One2many(
        'account.wht.certificate.line', 'income_type_id', 
        string='WHT Lines'
    )
    total_base = fields.Float(
        string='Total Base Amount', 
        compute='_compute_totals',
        help='Total Base Amount accumulated under this income type from confirmed WHT certificates.'
    )
    total_tax = fields.Float(
        string='Total Tax Amount', 
        compute='_compute_totals',
        help='Total Tax Amount accumulated under this income type from confirmed WHT certificates.'
    )

    @api.depends('certificate_line_ids.base_amount', 'certificate_line_ids.tax_amount', 'certificate_line_ids.certificate_id.state')
    def _compute_totals(self):
        for rec in self:
            lines = rec.certificate_line_ids.filtered(lambda line: line.certificate_id.state == 'done')
            rec.total_base = sum(lines.mapped('base_amount'))
            rec.total_tax = sum(lines.mapped('tax_amount'))
    
    # ประเภทแบบยื่นภาษีหัก ณ ที่จ่าย — ครบทุกประเภทตามมาตรฐานกรมสรรพากร
    pnd_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string='Default PND Type')
    
    display_name_full = fields.Char(
        string='Display Name', 
        compute='_compute_display_name_full', 
        store=True
    )

    @api.depends('code', 'name')
    def _compute_display_name_full(self):
        for rec in self:
            if rec.code and rec.name:
                rec.display_name_full = f"{rec.code}. {rec.name}"
            else:
                rec.display_name_full = rec.name or rec.code or 'New'

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, rec.display_name_full))
        return result


class AccountWHTCertificate(models.Model):
    _name = "account.wht.certificate"
    _description = "WHT Certificate"
    _rec_name = "certificate_no"
    
    _sql_constraints = [
        # COMPOSITE UNIQUENESS CONSTRAINT (Production-Safe)
        # Business-level uniqueness for Thai WHT system
        # Supports: multiple WHT lines, multiple income types, grouped certificates
        # Allows: payment retries, reconciliation retries, safe reprocessing
        # Prevents: duplicate certificates at business level
        ('certificate_business_unique', 
         'UNIQUE(company_id, partner_id, wht_type, income_type, payment_date, custom_key)',
         'Certificate with same business key already exists (company, partner, type, income type, date, operation)'),
         
        # CERTIFICATE NUMBER UNIQUENESS (Legal Requirement)
        ('certificate_company_unique', 
         'UNIQUE(certificate_no, company_id)', 
         'Certificate number must be unique per company (Thai legal requirement)'),
         
        # CUSTOM KEY UNIQUENESS (Idempotency Key)
        # Ensures that same operation cannot be repeated
        # Format: payment_id_bill_ids_tax_ids_wht_type_income_type_payment_date
        ('custom_key_unique', 
         'UNIQUE(custom_key)', 
         'Certificate with this idempotency key already exists (operation-level uniqueness)')
    ]
    
    # REMOVED: 'unique_payment_id' constraint was blocking multi-line WHT certificates
    # This constraint was too restrictive and did not support:
    # - Multiple WHT lines per payment
    # - Multiple income types per certificate
    # - Grouped certificates
    # - Safe retry operations

    certificate_no = fields.Char(
        string="Certificate No.",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: f"New - {self.env['ir.sequence'].next_by_code('wht.draft.seq') or fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')}",
    )
    issue_date = fields.Date(string="Issue Date", default=fields.Date.context_today)

    # General Information fields
    wht_book_no = fields.Char(string="WHT Book No.")
    wht_kind = fields.Selection([
        ('send', 'Send'),
        ('receive', 'Receive'),
    ], string="Type", default='send')
    wht_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string="WHT Type", default='pnd53')
    income_type = fields.Selection([
        ('service', 'Service'),
        ('rent', 'Rent'),
        ('other', 'Other'),
    ], string="Income Type", default='service')
    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal', tracking=True)
    sequence = fields.Integer(string="Sequence", default=0)

    # Payee Information
    partner_id = fields.Many2one("res.partner", string="Partner", required=True)
    partner_taxid = fields.Char(string="Partner Tax ID", copy=False)
    partner_address = fields.Text(string="Partner Address", copy=False)

    # Historical Snapshots - ข้อมูล ณ วันที่สร้างใบ WHT (ไม่เปลี่ยนแม้แก้ข้อมูลพาร์ทเนอร์ภายหลัง)
    partner_name_snapshot = fields.Char(
        string="ชื่อผู้รับ (Snapshot)",
        copy=False,
        help="Snapshot ชื่อพาร์ทเนอร์ ณ วันสร้างใบ WHT - ไม่เปลี่ยนแปลงแม้พาร์ทเนอร์จะแก้ชื่อภายหลัง"
    )
    bill_reference_snapshot = fields.Char(
        string="เลขที่ใบแจ้งหนี้ (Snapshot)",
        copy=False,
        help="Snapshot เลขที่ใบแจ้งหนี้ทั้งหมดที่ใช้ชำระ ณ วันสร้างใบ WHT"
    )
    branch_snapshot = fields.Char(
        string="สาขา/บริษัท (Snapshot)",
        copy=False,
        help="Snapshot ชื่อบริษัท/สาขา ณ วันสร้างใบ WHT"
    )
    invoice_date_snapshot = fields.Date(
        string="วันที่ใบแจ้งหนี้ (Snapshot)",
        copy=False,
        help="Snapshot วันที่ใบแจ้งหนี้แรก ณ วันสร้างใบ WHT"
    )

    # Source Traceability - สามารถ trace กลับไปหา Invoice Lines ต้นทางได้
    source_move_line_ids = fields.Many2many(
        "account.move.line",
        "wht_certificate_source_move_line_rel",
        "certificate_id",
        "move_line_id",
        string="Source Invoice Lines",
        copy=False,
        help="Invoice lines ต้นทางเพื่อ full audit traceability"
    )

    # Misc Information
    wht_reference = fields.Char(string="Reference", help="Source documents")
    user_pay_id = fields.Many2one('res.users', string="User Pay", default=lambda self: self.env.user)
    display_user_signature = fields.Boolean(string="Display User Signature?", default=True)
    display_company_seal = fields.Boolean(string="Display Company Seal?", default=True)
    pay_date = fields.Date(string="Pay Date", default=fields.Date.context_today)
    payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
        ondelete='cascade',
        readonly=True,
        help="Primary source payment (legacy single-payment reference — preserved for backward compat)"
    )
    payment_ids = fields.Many2many(
        'account.payment',
        'wht_certificate_payment_rel',
        'certificate_id',
        'payment_id',
        string='Payments',
        copy=False,
        help='All source payments for this certificate (grouped-payment architecture)'
    )
    move_id = fields.Many2one("account.move", string="Bill/Invoice (Legacy)")
    move_ids = fields.Many2many("account.move", string="Bills/Invoices")
    bill_count = fields.Integer(string="Bill Count", compute="_compute_bill_count")

    # Payer Information
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    company_taxid = fields.Char(related="company_id.vat", string="Company Tax ID")
    company_address = fields.Char(string="Company Address", compute='_compute_company_address', store=True)

    # Detail Lines
    line_ids = fields.One2many('account.wht.certificate.line', 'certificate_id', string="WHT Detail Lines")

    base_amount = fields.Monetary(string="Base Amount", compute="_compute_amounts", store=True)
    tax_amount = fields.Monetary(string="WHT Amount", compute="_compute_amounts", store=True)

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    
    # Idempotency Key - Production-Safe Custom Key Generation
    custom_key = fields.Char(
        string='Idempotency Key',
        index=True,
        copy=False,
        help='Business-level idempotency key. Format: payment_id_bills_hash_taxes_hash_wht_type_income_type_date'
    )
    
    def _generate_custom_key(self):
        """
        Generate business-safe idempotency key for WHT certificate.
        
        NEW FORMAT (Production-Safe):
        "{payments_hash}_{bills_hash}_{taxes_hash}_{wht_type}_{income_type}_{payment_date}"
        
        Components:
        - payments_hash: Hash of all payment IDs (supports grouped multi-payment batches)
        - bills_hash: Hash of related bill IDs (stable hash for grouped certificates)
        - taxes_hash: Hash of related tax IDs (supports multiple WHT rates)
        - wht_type: WHT document type (PND1, PND3, etc.)
        - income_type: Income type (service, rent, other)
        - payment_date: Payment date (date-based separation)
        
        This format supports:
        - Multiple WHT lines per certificate
        - Multiple income types per payment
        - Grouped certificates (multiple bills)
        - Payment retries (same key = same operation)
        - Reconciliation retries (stable hash)
        - Safe reprocessing (different keys for different operations)
        
        Returns:
            str: Idempotency key for business-level uniqueness
        """
        self.ensure_one()
        
        # Component 1: Payments hash (supports multiple payments in grouped flow)
        # Use payment_ids if available, fallback to payment_id for backward compat
        pmt_ids = self.payment_ids.mapped('id') if self.payment_ids else []
        if not pmt_ids and self.payment_id:
            pmt_ids = [self.payment_id.id]
        pmt_ids_sorted = sorted(pmt_ids)
        payments_hash = str(hash(tuple(pmt_ids_sorted))) if pmt_ids_sorted else '0'
        
        # Component 2: Bills Hash (stable hash for grouped certificates)
        # Use sorted IDs for consistent hash regardless of bill order
        bill_ids = self.move_ids.mapped('id') if self.move_ids else []
        bill_ids_sorted = sorted(bill_ids)
        bills_hash = str(hash(tuple(bill_ids_sorted))) if bill_ids else '0'
        
        # Component 3: Taxes Hash (supports multiple WHT rates)
        # Extract WHT tax IDs from certificate lines
        tax_ids = self.line_ids.mapped('wht_tax_id').mapped('id') if self.line_ids else []
        tax_ids_sorted = sorted(tax_ids)
        taxes_hash = str(hash(tuple(tax_ids_sorted))) if tax_ids else '0'
        
        # Component 4: WHT Type
        wht_type = self.wht_type or 'pnd53'
        
        # Component 5: Income Type
        income_type = self.income_type or 'service'
        
        # Component 6: Payment Date
        payment_date = self.pay_date or self.issue_date or fields.Date.context_today(self)
        payment_date_str = payment_date.strftime('%Y-%m-%d') if payment_date else 'unknown'
        
        # Generate composite key
        custom_key = f"{payments_hash}_{bills_hash}_{taxes_hash}_{wht_type}_{income_type}_{payment_date_str}"
        
        return custom_key
    
    @api.onchange('payment_id', 'payment_ids', 'move_ids', 'wht_type', 'income_type', 'pay_date')
    def _onchange_compute_custom_key(self):
        """
        Auto-compute custom key when key components change.
        
        This ensures idempotency key is always up-to-date and consistent.
        Called onchange to provide immediate feedback in UI.
        """
        for rec in self:
            rec.custom_key = rec._generate_custom_key()
    
    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for rec in self:
            if rec.partner_id:
                rec.partner_taxid = rec.partner_id.vat
                # Use _display_address(without_company=True) to exclude the partner name from the address string
                rec.partner_address = rec.partner_id._display_address(without_company=True)

    @api.depends('company_id')
    def _compute_company_address(self):
        for rec in self:
            if rec.company_id and rec.company_id.partner_id:
                # Use without_company=True to ensure the company name isn't duplicated in the address field
                rec.company_address = rec.company_id.partner_id._display_address(without_company=True)
            else:
                rec.company_address = ''
    
    @api.constrains('currency_id', 'move_ids', 'payment_id')
    def _check_currency_consistency(self):
        """Ensure certificate currency matches related moves and payments"""
        for rec in self:
            _logger.debug(
                "[WHT CERT] Checking currency consistency for certificate %s",
                rec.certificate_no if rec.certificate_no else f"ID: {rec.id}"
            )
            
            if rec.currency_id and rec.move_ids:
                # Check that all related moves have the same currency
                move_currencies = rec.move_ids.mapped('currency_id')
                if len(move_currencies) > 1:
                    _logger.error(
                        "[WHT CERT] Currency inconsistency: Certificate %s has multiple move currencies",
                        rec.certificate_no
                    )
                    raise UserError(_("All related invoices must have the same currency."))
                if move_currencies and move_currencies[0] != rec.currency_id:
                    _logger.error(
                        "[WHT CERT] Currency mismatch: Certificate %s (currency=%s) vs Move (currency=%s)",
                        rec.certificate_no, rec.currency_id.name, move_currencies[0].name
                    )
                    raise UserError(_("Certificate currency must match invoice currency."))
            
            if rec.currency_id and rec.payment_id:
                # Check that payment currency matches certificate currency
                if rec.payment_id.currency_id != rec.currency_id:
                    _logger.error(
                        "[WHT CERT] Currency mismatch: Certificate %s (currency=%s) vs Payment (currency=%s)",
                        rec.certificate_no, rec.currency_id.name, rec.payment_id.currency_id.name
                    )
                    raise UserError(_("Certificate currency must match payment currency."))
            
            _logger.debug(
                "[WHT CERT] Currency consistency check passed for certificate %s",
                rec.certificate_no if rec.certificate_no else f"ID: {rec.id}"
            )

    @api.depends('line_ids.base_amount', 'line_ids.tax_amount')
    def _compute_amounts(self):
        for rec in self:
            rec.base_amount = sum(rec.line_ids.mapped('base_amount'))
            rec.tax_amount = sum(rec.line_ids.mapped('tax_amount'))

    @api.depends("move_ids")
    def _compute_bill_count(self):
        for rec in self:
            rec.bill_count = len(rec.move_ids)

    def action_view_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills/Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'context': {'create': False},
        }

    @api.model
    def default_get(self, fields_list):
        res = super(AccountWHTCertificate, self).default_get(fields_list)
        res.update({'income_type': 'service'})
        return res

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Cannot confirm a certificate that is not in draft state"))
            if rec.certificate_no not in ('New', 'Draft') and not (rec.certificate_no and str(rec.certificate_no).startswith('New -')):
                raise UserError(_("Certificate number already assigned"))

            # Ensure custom key is computed before confirming
            if not rec.custom_key:
                rec.custom_key = rec._generate_custom_key()

            # Use database lock for sequence generation
            try:
                _logger.info(
                    "[WHT CERT] Generating certificate number for certificate %s (ID: %d)",
                    rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", rec.id
                )
                self.env.cr.execute(
                    "SELECT id FROM account_wht_certificate WHERE id = %s FOR UPDATE",
                    (rec.id,)
                )
                rec.certificate_no = self.env['ir.sequence'].next_by_code('account.wht.certificate') or rec.certificate_no
                rec.state = 'done'
                _logger.info(
                    "[WHT CERT] Certificate number generated: %s for certificate %s",
                    rec.certificate_no, rec.certificate_no if rec.certificate_no else f"ID: {rec.id}"
                )
            except Exception as e:
                _logger.error(
                    "[WHT CERT] ERROR: Failed to generate certificate number for certificate %s (ID: %d): %s",
                    rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", rec.id, str(e), exc_info=True
                )
                raise UserError(_("Failed to generate certificate number. Please try again."))

    def write(self, vals):
        """Prevent modification of critical fields after confirmation"""
        for rec in self:
            if rec.state == 'done' and not self.env.context.get('allow_historical_edit'):
                # List of fields that cannot be modified after confirmation
                protected_fields = ['certificate_no', 'move_ids', 'payment_id', 'payment_ids', 'custom_key', 'wht_type', 'wht_pay_type', 'partner_taxid', 'partner_address', 'partner_name_snapshot', 'bill_reference_snapshot', 'branch_snapshot', 'invoice_date_snapshot']
                if any(field in vals for field in protected_fields):
                    _logger.warning(
                        "[WHT CERT] PROTECTED: Attempt to modify protected fields on confirmed certificate %s: %s",
                        rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", ', '.join([f for f in protected_fields if f in vals])
                    )
                    raise UserError(_("Cannot modify %s for confirmed certificate. Please cancel it first or use action_recompute_from_bills.") % ', '.join(protected_fields))
        return super(AccountWHTCertificate, self).write(vals)

    def action_recompute_from_bills(self):
        """ดึงรายการภาษีใหม่จากบิลที่เชื่อมโยง — ใช้ได้เฉพาะสถานะ Draft"""
        _logger.info("[WHT CERT] RECOMPUTE: Recomputing %d certificate(s) from bills", len(self))
        
        for rec in self:
            if rec.state != 'draft':
                _logger.warning(
                    "[WHT CERT] SKIP: Certificate %s is not in draft state (state=%s)",
                    rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", rec.state
                )
                continue
            if not rec.move_ids:
                _logger.warning(
                    "[WHT CERT] SKIP: Certificate %s has no associated bills",
                    rec.certificate_no if rec.certificate_no else f"ID: {rec.id}"
                )
                continue

            _logger.info(
                "[WHT CERT] RECOMPUTE: Recomputing certificate %s with %d bills",
                rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", len(rec.move_ids)
            )

            new_lines = []
            for move in rec.move_ids:
                for inv_line in move.invoice_line_ids:
                    for wht in inv_line.wht_tax_ids:
                        try:
                            calc = WHTCalculationService.compute_wht_by_pay_type(
                                inv_line.price_subtotal,
                                wht.amount,
                                move.wht_pay_type or 'normal',
                            )
                        except ValueError:
                            # e.g. rate=100% for gross_up_forever
                            continue
                        l_base = calc['base']
                        l_tax  = calc['wht']
                        new_lines.append((0, 0, {
                            'income_type_id': wht.income_type_id.id if wht.income_type_id else False,
                            'income_type_code': wht.income_type_id.code if wht.income_type_id else '',
                            'income_type_name': wht.income_type_id.name if wht.income_type_id else '',
                            'income_type_text': wht.description or wht.name or 'Service',
                            'name': wht.name,
                            'base_amount': l_base,
                            'tax_amount': l_tax,
                            'invoice_move_id': move.id,
                            'wht_pay_type': move.wht_pay_type,
                        }))

            # ลบรายการเดิมออกก่อนแล้วแทนใหม่
            rec.write({
                'line_ids': [(5, 0, 0)] + new_lines,
                'wht_reference': ', '.join(rec.move_ids.mapped('name')),
            })
            _logger.info(
                "[WHT CERT] RECOMPUTE SUCCESS: Certificate %s recomputed with %d new lines",
                rec.certificate_no if rec.certificate_no else f"ID: {rec.id}", len(new_lines)
            )
        
        _logger.info("[WHT CERT] RECOMPUTE END: Recomputation flow completed")

    def action_cancel(self):
        _logger.info("[WHT CERT] CANCEL: Canceling %d certificate(s)", len(self))
        for rec in self:
            _logger.info(
                "[WHT CERT] CANCEL: Certificate %s (ID: %d, State: %s) → cancel",
                rec.name if rec.name else f"ID: {rec.id}", rec.id, rec.state
            )
            rec.state = 'cancel'
        _logger.info("[WHT CERT] CANCEL: Cancelation completed for %d certificate(s)", len(self))

    def action_draft(self):
        """Reset certificate back to draft state"""
        _logger.info("[WHT CERT] DRAFT: Resetting %d certificate(s) to draft state", len(self))
        for rec in self:
            if rec.state not in ['done', 'cancel']:
                _logger.warning(
                    "[WHT CERT] SKIP: Cannot reset certificate %s to draft (state=%s, expected=done/cancel)",
                    rec.name if rec.name else f"ID: {rec.id}", rec.state
                )
                raise UserError(_("Cannot set to draft a certificate that is not in done or cancel state"))
            _logger.info(
                "[WHT CERT] DRAFT: Certificate %s (ID: %d, State: %s) → draft",
                rec.name if rec.name else f"ID: {rec.id}", rec.id, rec.state
            )
            rec.state = 'draft'
        _logger.info("[WHT CERT] DRAFT: Reset to draft completed for %d certificate(s)", len(self))

    def action_print_50_bis(self):
        for rec in self:
            if rec.state != 'done':
                raise models.ValidationError(_("Cannot print 50 Bis unless the WHT Certificate is Done. / ไม่สามารถพิมพ์ 50 ทวิได้หากสถานะ WHT Certificate ยังไม่เสร็จสิ้น (Done)"))
        return self.env.ref("account_WHT.action_report_wht_50_bis").report_action(self)

    def action_print_50tawi(self):
        for rec in self:
            if rec.state != 'done':
                raise models.ValidationError(_("Cannot print 50 Tawi unless the WHT Certificate is Done. / ไม่สามารถพิมพ์ 50 ทวิได้หากสถานะ WHT Certificate ยังไม่เสร็จสิ้น (Done)"))
        return self.env.ref('account_WHT.action_wht_50tawi').report_action(self)

    def action_preview_50tawi(self):
        """Preview ในรูปแบบ HTML เพื่อช่วยในการตรวจสอบรูปแบบ (Format)"""
        self.ensure_one()
        action = self.env.ref('account_WHT.action_wht_50tawi').report_action(self)
        action['report_type'] = 'qweb-html'
        return action

    def action_send_email(self):
        self.ensure_one()
        if self.state == 'draft':
            raise models.ValidationError(_("Cannot send email for a draft WHT Certificate. Please confirm it first."))

        ctx = {
            'default_model': 'account.wht.certificate',
            'default_res_ids': self.ids,
            'default_use_template': False,
            'default_composition_mode': 'comment',
            'default_partner_ids': [(6, 0, [self.partner_id.id])] if self.partner_id else [],
            'default_subject': f'หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ) - {self.certificate_no}',
            'default_body': f'<p>เรียน {self.partner_id.name or "ท่านคู่ค้า"},</p><p>บริษัทได้จัดทำและส่งหนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ) เลขที่ <b>{self.certificate_no}</b> มาพร้อมกับอีเมลฉบับนี้</p><br/><p>ขอแสดงความนับถือ</p>',
        }

        report_action = self.env.ref('account_WHT.action_wht_50tawi', raise_if_not_found=False)
        if report_action:
            pdf_content = self.env['ir.actions.report']._render_qweb_pdf('account_WHT.action_wht_50tawi', [self.id])[0]
            attachment = self.env['ir.attachment'].create({
                'name': f'WHT_50Tawi_{self.certificate_no}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'account.wht.certificate',
                'res_id': self.id,
                'mimetype': 'application/pdf'
            })
            ctx['default_attachment_ids'] = [(6, 0, [attachment.id])]

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'target': 'new',
            'context': ctx,
        }

    def action_export_rd_txt(self):
        lines = []
        for rec in self:
            tax_id = rec.partner_taxid or ''
            name = rec.partner_id.name or ''
            amount = "{:.2f}".format(rec.base_amount or 0.0)
            tax = "{:.2f}".format(rec.tax_amount or 0.0)
            # Use pipe '|' delimiter as per user requirement (tax_id | name | amount | tax)
            line = f"{tax_id}|{name}|{amount}|{tax}"
            lines.append(line)
            
        # Convert to TIS-620 or UTF-8. Odoo default is UTF-8, but RD often requires TIS-620/Windows-874.
        # We'll use windows-874 to be safe with Thai RD systems if requested, otherwise utf-8.
        # But let's stick to utf-8 unless specified. RD modern systems accept UTF-8 but some legacy require TIS-620.
        # Since it's a simple export, let's use utf-8.
        txt_content = "\r\n".join(lines)
        
        attachment = self.env['ir.attachment'].create({
            'name': 'RD_Export.txt',
            'type': 'binary',
            'datas': base64.b64encode(txt_content.encode('utf-8')),
            'res_model': 'account.wht.certificate',
            'mimetype': 'text/plain'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def get_wht_background_base64(self):
        """Helper to get static background as base64 for wkhtmltopdf reliability"""
        addon_path = get_module_resource('account_WHT', 'static', 'src', 'img', '50tawi_bg.png')
        if addon_path and os.path.exists(addon_path):
            with open(addon_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('ascii')
                return f"data:image/png;base64,{img_data}"
        return ""

    def get_grouped_income_lines(self):
        """Helper for 50 Tawi Report to group line amounts by income type code."""
        self.ensure_one()
        groups = {}
        for line in self.line_ids:
            code = line.income_type_code or '6'
            if code not in groups:
                groups[code] = {
                    'code': code,
                    'name': line.name,
                    'date': line.pay_date or self.issue_date,
                    'base_amount': 0.0,
                    'tax_amount': 0.0,
                }
            groups[code]['base_amount'] += line.base_amount
            groups[code]['tax_amount'] += line.tax_amount
        return groups.values()


class AccountWHTCertificateLine(models.Model):
    _name = "account.wht.certificate.line"
    _description = "WHT Certificate Line"
    _sql_constraints = [
        ('positive_base_amount', 'CHECK(base_amount >= 0)', 'Base amount cannot be negative'),
        ('positive_tax_amount', 'CHECK(tax_amount >= 0)', 'Tax amount cannot be negative')
    ]


    certificate_id = fields.Many2one('account.wht.certificate', ondelete='cascade')
    invoice_move_id = fields.Many2one(
        'account.move',
        string='From Bill/Invoice',
        ondelete='set null',
        help='Source bill/invoice for this line (for multi-bill payment traceability)',
    )
    income_type_id = fields.Many2one('wht.income.type', string="Income Type")
    income_type_code = fields.Char(
        string="Income Type Code", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=True,
        help="Historical data - cannot be modified after creation"
    )
    income_type_name = fields.Char(
        string="Income Type Name", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=True,
        help="Historical data - cannot be modified after creation"
    )
    income_type_text = fields.Char(
        string="Legacy Income Type", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=True,
        help="Historical data - cannot be modified after creation"
    )
    name = fields.Char(string="Name")
    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal')
    pay_date = fields.Date(string="Pay Date")
    base_amount = fields.Monetary(string="Base Amount")
    tax_amount = fields.Monetary(string="WHT Amount")
    currency_id = fields.Many2one(related='certificate_id.currency_id')

    @api.depends('income_type_id')
    def _compute_income_type_fields(self):
        for rec in self:
            if rec.income_type_id:
                rec.income_type_code = rec.income_type_id.code or ''
                rec.income_type_name = rec.income_type_id.name or ''
                rec.income_type_text = rec.income_type_id.name or ''
            else:
                if not rec.income_type_code:
                    rec.income_type_code = ''
                if not rec.income_type_name:
                    rec.income_type_name = ''
                if not rec.income_type_text:
                    rec.income_type_text = ''
    
    def write(self, vals):
        for rec in self:
            if rec.certificate_id.state == 'done' and not self.env.context.get('allow_historical_edit'):
                raise UserError(_("Cannot modify certificate lines for confirmed certificates"))
        return super(AccountWHTCertificateLine, self).write(vals)


def _default_wht_tax_group(self):
    return self.env["account.tax.group"].search([], limit=1)


class AccountWHT(models.Model):
    _name = "account.wht"
    _description = "Withholding Tax"

    name = fields.Char(string="Tax Name", required=True)
    tax_code = fields.Char(string="Tax Code")

    account_id = fields.Many2one(
        "account.account",
        string="WHT Account on Invoices",
        ondelete="restrict",
    )
    refund_account_id = fields.Many2one(
        "account.account", string="WHT Account on Credit Notes", ondelete="restrict"
    )
    income_type_id = fields.Many2one("wht.income.type", string="Income Type")
    description = fields.Text(string="Legacy Income Type")
    active = fields.Boolean(default=True)
    income_account_id = fields.Many2one("account.account", string="Income Account")
    expense_account_id = fields.Many2one("account.account", string="Expense Account")
    amount = fields.Float(string="Amount", required=True, digits=(16, 4), default=0.0)
    type_tax_use = fields.Selection(
        [
            ("sale", "Sales"),
            ("purchase", "Purchases"),
            ("none", "None"),
            ("tax", "Tax on Tax"),
        ],
        string="Tax Type",
        default="sale",
        required=True,
    )
    tax_application = fields.Selection(
        [("invoice", "Invoice"), ("payment", "Payment")],
        string="Tax Application",
        default="payment",
    )
    sale_tax_id = fields.Many2one("account.tax", string="Tax")
    wht_type = fields.Selection(
        [
            ('pnd1',         'ภ.ง.ด.1'),
            ('pnd1k',        'ภ.ง.ด.1ก'),
            ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
            ('pnd2',         'ภ.ง.ด.2'),
            ('pnd2k',        'ภ.ง.ด.2ก'),
            ('pnd3',         'ภ.ง.ด.3'),
            ('pnd3k',        'ภ.ง.ด.3ก'),
            ('pnd53',        'ภ.ง.ด.53'),
        ],
        string="WHT Type",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    tax_group_id = fields.Many2one(
        "account.tax.group",
        string="Tax Group",
        default=_default_wht_tax_group,
        required=True,
    )

    @api.onchange("account_id")
    def onchange_account_id(self):
        self.refund_account_id = self.account_id
