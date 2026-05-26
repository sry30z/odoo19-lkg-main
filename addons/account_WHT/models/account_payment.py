# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _, Command
from odoo.exceptions import UserError
from .wht_calculation_service import WHTCalculationService

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _create_wht_certificate_after_payment_creation(self):
        """
        Orchestrator: Payment-Centric WHT Certificate Creation (Production-Grade)

        รับผิดชอบ:
          - Guards (ประเภท payment, ตรวจสอบ wizard)
          - Idempotency check (ป้องกันใบซ้ำ)
          - เรียก WHTCalculationService เพื่อเตรียมข้อมูลทั้งหมด
          - ประกอบ cert_vals และ Create + Confirm

        การคำนวณ / ค้นหา / snapshot ทั้งหมดถูกมอบหมายให้
        WHTCalculationService (single source of truth)

        ไม่ raise exception — WHT failure ต้องไม่ทำให้ payment ล้มเหลว
        """
        _logger.info("[WHT CERT] Processing certificate for payment %s (id=%s)",
                     self.name or '', self.id)

        # ── Guard: only outbound vendor payments ──────────────────────────────
        if self.payment_type != 'outbound':
            return
        if self.partner_type not in ('supplier', 'vendor'):
            return

        # ── Guard: get wizard from context ────────────────────────────────────
        wizard_id = self.env.context.get('wht_wizard_id')
        if not wizard_id:
            _logger.info("[WHT SKIP] No wht_wizard_id in context for payment %s", self.name)
            return

        wizard = self.env['account.payment.register'].browse(wizard_id).exists()
        if not wizard:
            _logger.info("[WHT SKIP] Wizard %s no longer exists for payment %s",
                         wizard_id, self.name)
            return

        if not getattr(wizard, 'is_wht', False) or not wizard.wht_line_ids:
            _logger.info("[WHT SKIP] Wizard has no WHT lines for payment %s", self.name)
            return

        # ── Idempotency: abort if certificate already exists ──────────────────
        # wht_all_payment_ids ถูกส่งมาโดย _create_payments() เมื่อ wizard สร้างหลาย payment
        # (non-grouped flow) — ตรวจสอบ ALL IDs เพื่อป้องกัน duplicate หลัง partial failure
        _all_payment_ids = list(self.env.context.get('wht_all_payment_ids') or [self.id])
        existing = self.env['account.wht.certificate'].search([
            '&',
            '|',
            ('payment_id', 'in', _all_payment_ids),
            ('payment_ids', 'in', _all_payment_ids),
            ('state', '!=', 'cancel'),
        ], limit=1)
        if existing:
            _logger.info(
                "[WHT SKIP] Certificate %s already exists for payment batch %s",
                existing.certificate_no, _all_payment_ids,
            )
            return

        # ── All creation wrapped in try/except — payment must NEVER fail ──────
        try:
            service = WHTCalculationService(self.env)

            # STEP 1: ค้นหาใบแจ้งหนี้ต้นทาง
            invoices = service.discover_bills(wizard, self)

            # STEP 2: บันทึก snapshot ข้อมูลพาร์ทเนอร์
            partner_snap = service.partner_snapshot(self.partner_id)

            # STEP 3: บันทึก snapshot ข้อมูลใบแจ้งหนี้
            bill_snap = service.bill_snapshot(invoices, self)

            # STEP 4: สร้าง WHT detail lines
            lines_vals = service.build_detail_lines(wizard, invoices, self)

            # STEP 5: รวบรวม source line IDs สำหรับ audit trail
            src_line_ids = service.source_line_ids(invoices)

            # STEP 6: ประกอบค่า certificate
            cert_vals = {
                # Core
                'payment_id':  self.id,
                'partner_id':  self.partner_id.id if self.partner_id else False,
                'issue_date':  self.date,
                'pay_date':    self.date,
                'wht_type':    wizard.wht_type or 'pnd53',
                'wht_pay_type': wizard.wht_pay_type or 'normal',
                'state':       'draft',
                # Partner + bill snapshots จาก service
                **partner_snap,
                **bill_snap,
                # Detail lines
                'line_ids': lines_vals,
            }

            if invoices:
                cert_vals['move_ids'] = [(6, 0, invoices.ids)]
            # เชื่อม ALL payments ใน batch (grouped-payment architecture)
            cert_vals['payment_ids'] = [(6, 0, _all_payment_ids)]
            if src_line_ids:
                cert_vals['source_move_line_ids'] = [(6, 0, src_line_ids)]

            # STEP 7: Create + Confirm
            _logger.info(
                "[WHT CERT] Creating certificate: partner=%s, bills=%s, lines=%d",
                partner_snap.get('partner_name_snapshot', ''),
                bill_snap.get('bill_reference_snapshot', ''),
                len(lines_vals),
            )
            certificate = self.env['account.wht.certificate'].create(cert_vals)
            _logger.info(
                "[WHT CERT] Certificate created in draft: %s (id=%d)",
                certificate.certificate_no, certificate.id,
            )
            # Auto-confirm: separate try/except so cert creation survives if confirm fails
            try:
                self.env.flush_all()  # ensure cert row is in DB before FOR UPDATE
                certificate.action_confirm()
                _logger.info(
                    "[WHT CERT] Auto-confirmed %s for payment %s",
                    certificate.certificate_no, self.name,
                )
            except Exception as confirm_err:
                _logger.warning(
                    "[WHT CERT] Auto-confirm failed for %s — remaining in draft: %s",
                    certificate.certificate_no, str(confirm_err),
                )
                # Certificate stays in draft for manual confirmation; payment unaffected

        except Exception as e:
            _logger.exception(
                "[WHT ERROR] Failed to create WHT certificate for payment %s: %s",
                self.name or self.id, str(e),
            )
            # CRITICAL: ไม่ re-raise — payment ต้องสำเร็จไม่ว่า WHT จะล้มเหลว

    def _wht_domain(self):
        # แสดง WHT ทุกตัวที่ใช้กับการชำระเงิน (ทั้งฝั่ง Customer และ Vendor)
        return [["tax_application", "=", "payment"]]

    wht_ids = fields.Many2many("account.wht", domain=_wht_domain)
    override_wht = fields.Boolean("Override WHT")

    payment_amount = fields.Monetary(related="move_id.amount_total", string="Total ")
    wht_amount = fields.Monetary(string="WHT amount", compute="compute_wht_amount")
    after_wh_payment_amount = fields.Monetary(
        string="Net Payment", compute="compute_wht_amount"
    )
    wht_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string='WHT Type', tracking=True)
    inv_created = fields.Boolean(default=False)
    wht_certificate_count = fields.Integer(compute="_compute_wht_certificate_count")

    def _compute_wht_certificate_count(self):
        for payment in self:
            payment.wht_certificate_count = self.env["account.wht.certificate"].search_count([
                '&',
                '|',
                ("payment_id", "=", payment.id),
                ("payment_ids", "in", [payment.id]),
                ("state", "!=", "cancel"),
            ])

    def action_view_wht_certificates(self):
        self.ensure_one()
        return {
            "name": _("WHT Certificates"),
            "type": "ir.actions.act_window",
            "res_model": "account.wht.certificate",
            "view_mode": "list,form",
            "domain": [
                '&',
                '|',
                ("payment_id", "=", self.id),
                ("payment_ids", "in", [self.id]),
                ("state", "!=", "cancel"),
            ],
            "context": {
                "default_payment_id": self.id,
                "default_payment_ids": [(4, self.id)],
                "default_partner_id": self.partner_id.id,
            },
        }

    @api.onchange("override_wht")
    def _onchange_override_wht(self):
        if self.override_wht:
            self.wht_ids = False

    @api.onchange("wht_ids")
    def _onchange_wht_ids(self):
        domain = [("tax_application", "=", "payment")]
        if self.partner_type == "customer":
            domain.append(("type_tax_use", "in", ("sale", "tax")))
        elif self.partner_type == "supplier":
            domain.append(("type_tax_use", "in", ("purchase", "tax")))

        return {"domain": {"wht_ids": domain}}

    def _get_wht_payment_ratio(self, payment, invoices):
        """ คำนวณสัดส่วนการชำระเงินเทียบกับยอดรวมใบแจ้งหนี้ (net total) """
        if not invoices:
            return 0.0
        target_net = sum(
            inv.amount_net_total if hasattr(inv, 'amount_net_total') and inv.amount_net_total else inv.amount_total
            for inv in invoices
        )
        if not target_net:
            return 0.0
        ratio = payment.amount / target_net
        return min(1.0, max(0.0, ratio))

    @api.depends("amount", "wht_ids")
    def compute_wht_amount(self):
        # WHT amounts on payment are computed via account.payment.register (wizard).
        # Direct computation from invoices is handled during the payment registration
        # workflow. Here we ensure the stored fields always have a valid default.
        for payment in self:
            payment.wht_amount = 0.00
            payment.after_wh_payment_amount = payment.amount
