# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from .wht_calculation_service import WHTCalculationService

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    tax_line_ids = fields.One2many(
        "account.move.tax", "move_id", string="Tax Lines", readonly=True, copy=True
    )
    # Removed state redefinition as it breaks core Odoo functionality

    wht_line_ids = fields.One2many(
        "account.move.wht", "move_id", string="WHT Lines", readonly=True
    )
    wht_bill_created = fields.Boolean()

    wht_pay_type = fields.Selection(
        [
            ("normal", "หัก ณ ที่จ่าย"),
            ("gross_up_forever", "ออกให้ตลอด"),
            ("gross_up_once", "ออกให้ครั้งเดียว"),
        ],
        string="WHT Pay Type",
        default="normal",
        tracking=True,
    )

    # Note: Removed unsafe override of payment_state selection that forced
    # 'in_payment' to display as 'Paid'. This was hiding unreconciled payments
    # from bank reconciliation and producing incorrect aging reports.

    taxes_line_ids = fields.One2many("account.move.tax.lines", "move_id")
    wht_certificate_count = fields.Integer(compute="_compute_wht_certificate_count")

    # SME-friendly display label for payment status.
    # This is a DISPLAY-ONLY computed field — it never overrides payment_state or any
    # accounting logic. Safe to use in views and reports without side-effects.
    payment_status_display_label = fields.Char(
        string="สถานะการชำระ",
        compute="_compute_payment_status_display_label",
        store=False,
        help="Human-readable payment status for display in bills and reports.",
    )

    def _compute_payment_status_display_label(self):
        _LABEL_MAP = {
            "not_paid": "ยังไม่ชำระ",
            "in_payment": "ชำระแล้ว",
            "paid": "ชำระแล้ว",
            "partial": "ชำระบางส่วน",
            "reversed": "ยกเลิก/Reversed",
            "invoicing_legacy": "Legacy",
        }
        for move in self:
            state = move.payment_state or "not_paid"
            move.payment_status_display_label = _LABEL_MAP.get(state, state)

    def _compute_wht_certificate_count(self):
        for move in self:
            move.wht_certificate_count = self.env[
                "account.wht.certificate"
            ].search_count([("move_ids", "in", move.ids), ("state", "!=", "cancel")])

    def action_view_wht_certificates(self):
        """Smart button บน Bill เพื่อดู WHT Certificates ทั้งหมด"""
        self.ensure_one()
        return {
            "name": _("WHT Certificates"),
            "type": "ir.actions.act_window",
            "res_model": "account.wht.certificate",
            "view_mode": "list,form",
            "domain": [("move_ids", "in", self.ids)],
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_move_ids": [(6, 0, self.ids)],
            },
        }

    wht_base_amount = fields.Monetary(
        string="WHT Base", compute="_compute_wht_totals", store=True
    )
    wht_amount = fields.Monetary(
        string="WHT Amount", compute="_compute_wht_totals", store=True
    )
    wht_net_total = fields.Monetary(
        string="Net Total", compute="_compute_wht_totals", store=True
    )
    amount_due = fields.Monetary(
        string="Amount Due", compute="_compute_wht_totals", store=True
    )

    # Legacy fields mapping (to avoid breaking views before update)
    amount_wht_base = fields.Monetary(related="wht_base_amount")
    amount_wht = fields.Monetary(related="wht_amount")
    amount_net_total = fields.Monetary(related="wht_net_total")

    @api.depends(
        "invoice_line_ids.price_total", "invoice_line_ids.wht_tax_ids", "wht_pay_type"
    )
    def _compute_wht_totals(self):
        """
        Compute WHT totals using the centralized Service Layer.

        This replaces the previous duplicate calculation logic with a single
        source of truth service, ensuring deterministic behavior.
        """
        for move in self:
            if move.move_type not in [
                "in_invoice",
                "out_invoice",
                "in_refund",
                "out_refund",
            ]:
                # Reset for non-invoice moves
                move.wht_base_amount = 0.0
                move.wht_amount = 0.0
                move.wht_net_total = sum(move.invoice_line_ids.mapped("price_total"))
                move.amount_due = move.wht_net_total
                continue

            # Use the centralized WHT Calculation Service
            service = self.env["wht.calculation.service"]
            try:
                invoice_wht = service.calculate_invoice_wht(move)

                total_amount = sum(move.invoice_line_ids.mapped("price_total"))

                move.wht_base_amount = invoice_wht["total"]["base"]
                move.wht_amount = invoice_wht["total"]["wht"]
                move.amount_due = invoice_wht["total"]["total"]
                move.wht_net_total = invoice_wht["total"]["net"]

            except Exception as e:
                _logger.error(
                    "[WHT CALC] ERROR: WHT calculation failed for move %s (ID: %d): %s",
                    move.name,
                    move.id,
                    str(e),
                    exc_info=True,
                )
                # Fallback to zero on error to prevent blocking
                move.wht_base_amount = 0.0
                move.wht_amount = 0.0
                move.wht_net_total = sum(move.invoice_line_ids.mapped("price_total"))
                move.amount_due = move.wht_net_total

    def create_wht_line(self, line):
        # PHASE 2 HOTFIX: company_id ต้องถูกส่งใน vals ทุกครั้ง
        # ไม่พึ่ง compute หรือ default เพราะ validation เกิดก่อน compute ใน Odoo 18
        amount = 0
        if self.move_type in ["out_invoice", "in_refund"]:
            amount = line.debit
        elif self.move_type in ["in_invoice", "out_refund"]:
            amount = line.credit

        if amount:
            self.wht_line_ids.create(
                {
                    "name": "Withholding Tax",
                    "account_id": line.account_id.id,
                    "amount": amount,
                    "move_id": self.id,
                    # HOTFIX: explicit company_id — never rely on compute or default timing
                    "company_id": self.company_id.id or self.env.company.id,
                }
            )

    @api.model_create_multi
    def create(self, vals_list):
        import traceback
        _logger.warning(">>> TRACE [create] \n%s", ''.join(traceback.format_stack()[:-1]))
        moves = super(AccountMove, self).create(vals_list)
        for move in moves:
            if move.move_type in [
                "out_invoice",
                "in_invoice",
                "out_refund",
                "in_refund",
            ]:
                move.with_context(skip_wht_recompute=True).on_change_tax_ids()
                move.with_context(skip_wht_recompute=True)._onchange_invoice_line_ids()
        return moves

    def write(self, vals):
        import traceback
        _logger.warning(">>> TRACE [write] keys: %s\n%s", list(vals.keys()), ''.join(traceback.format_stack()[:-1]))
        res = super(AccountMove, self).write(vals)
        if any(f in vals for f in ["invoice_line_ids", "wht_pay_type", "line_ids"]):
            if not self.env.context.get("skip_wht_recompute"):
                for move in self:
                    if move.move_type in [
                        "out_invoice",
                        "in_invoice",
                        "out_refund",
                        "in_refund",
                    ]:
                        move.with_context(skip_wht_recompute=True).on_change_tax_ids()
                        move.with_context(
                            skip_wht_recompute=True
                        )._onchange_invoice_line_ids()
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
                if wht_tax.tax_application == "invoice":
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
            if move.move_type in [
                "in_invoice",
                "out_invoice",
                "in_refund",
                "out_refund",
            ]:
                certs = self.env["account.wht.certificate"].search(
                    [("move_ids", "in", move.ids), ("state", "!=", "cancel")]
                )
                for cert in certs:
                    cert.action_cancel()

            # ถ้ายกเลิก payment move → ยกเลิก WHT certs ที่เชื่อมกับ payment นี้
            # ค้นหาด้วย OR domain ครอบคลุมทั้ง payment_id (Many2one legacy)
            # และ payment_ids (Many2many ใหม่) เพื่อไม่ให้ cert หลุด
            if move.payment_id:
                payment_pk = move.payment_id.id
                certs = self.env["account.wht.certificate"].search(
                    [
                        ("state", "!=", "cancel"),
                        "|",
                        ("payment_id", "=", payment_pk),
                        ("payment_ids", "in", [payment_pk]),
                    ]
                )
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
        service = self.env["wht.calculation.service"]

        # Determine if this is tax-on-tax
        if (
            wht.is_vat_based_wht()
            and tax_line
            and tax_line.id in wht.sale_tax_id.ids
        ):
            calc_result = service.calculate_tax_on_tax_wht(
                base_amount, wht.amount, self.wht_pay_type
            )
        else:
            calc_result = service.calculate_wht(
                base_amount, wht.amount, self.wht_pay_type
            )

        wht_amount = calc_result["wht"]
        wht_expense_amount = calc_result["gross_up"]

        if wht_amount:
            # WHT Liability/Asset Line
            debit = (
                wht_amount if self.move_type in ["out_invoice", "in_refund"] else 0.0
            )
            credit = (
                wht_amount if self.move_type in ["in_invoice", "out_refund"] else 0.0
            )

            line_ids.append(
                (
                    0,
                    0,
                    {
                        "name": wht.name,
                        "account_id": wht.account_id.id,
                        "debit": debit,
                        "credit": credit,
                        "partner_id": self.partner_id.id,
                        "display_type": "product",
                        "wht_tax_ids": [(6, 0, [wht.id])],
                        "is_wht_line": True,
                    },
                )
            )

            # WHT Expense/Income Line for Gross-Up
            if wht_expense_amount > 0:
                exp_account = (
                    wht.expense_account_id.id
                    if self.move_type in ["in_invoice", "out_refund"]
                    else wht.income_account_id.id
                )
                if not exp_account:
                    exp_account = wht.account_id.id

                exp_debit = (
                    wht_expense_amount
                    if self.move_type in ["in_invoice", "out_refund"]
                    else 0.0
                )
                exp_credit = (
                    wht_expense_amount
                    if self.move_type in ["out_invoice", "in_refund"]
                    else 0.0
                )

                line_ids.append(
                    (
                        0,
                        0,
                        {
                            "name": f"{wht.name} (Gross-up Absorbed)",
                            "account_id": exp_account,
                            "debit": exp_debit,
                            "credit": exp_credit,
                            "partner_id": self.partner_id.id,
                            "display_type": "product",
                            "is_wht_line": True,
                        },
                    )
                )

        return line_ids

    def generate_wht_move_lines(self, wht, line, line_ids):
        """
        สร้าง WHT journal lines สำหรับประเภท 'invoice' (tax-on-tax)

        หมายเหตุ: แก้ bug เดิมที่ round อัตรา (rate) แทนที่จะ round ผลลัพธ์
          เดิม: price_subtotal * round(amount/100, 2)  ← round อัตรา 7.5% → 0.08 (ผิด!)
          ใหม่: round(price_subtotal * (amount/100), 2) ← round ผลลัพธ์ถูกต้อง
        """
        if wht.tax_application == "invoice":
            tax_amount = 0
            if line.tax_ids:
                for tax_line in line.tax_ids:
                    # คำนวณ VAT/tax amount เพื่อใช้เป็นฐานสำหรับ WHT ประเภท tax-on-tax
                    # ต้อง round ที่ผลลัพธ์ ไม่ใช่ที่อัตรา
                    tax_amount = round(
                        line.price_subtotal * (tax_line.amount / 100.0), 2
                    )
                    return self.append_entry(
                        wht, tax_amount, line, line_ids, tax_line=tax_line
                    )
            else:
                return self.append_entry(wht, tax_amount, line, line_ids, tax_line=None)
        return line_ids

    @api.onchange("invoice_line_ids")
    def _onchange_invoice_line_ids(self):
        import traceback
        _logger.warning(">>> TRACE [_onchange_invoice_line_ids] move_id: %s, _origin: %s\n%s", self.id, self._origin.id if self._origin else None, ''.join(traceback.format_stack()[:-1]))
        invoice_line_ids = self.invoice_line_ids

        line_ids = []
        for line in invoice_line_ids:
            if line.wht_tax_ids:
                for wht in line.wht_tax_ids:
                    line_ids = self.generate_wht_move_lines(wht, line, line_ids)

        wht_delete_ops = [
            (2, wht.id) for wht in self.line_ids.filtered(lambda l: l.is_wht_line)
        ]

        if line_ids or wht_delete_ops:
            self.line_ids = wht_delete_ops + line_ids
            self.invoice_line_ids = invoice_line_ids

        return {}

    def action_register_payment(self):
        """Open the account.payment.register wizard to pay the selected journal entries.
        :return: An action opening the account.payment.register wizard.
        """
        res = super(AccountMove, self).action_register_payment()
        wht_lines = self.invoice_line_ids.filtered(
            lambda l: not l.display_type or l.display_type == "product"
        ).wht_tax_ids.filtered(lambda s: s.tax_application == "payment")
        if wht_lines:
            if "context" not in res:
                res["context"] = {}
            res["context"]["default_wht_ids"] = wht_lines.ids
        return res

    @api.onchange("invoice_line_ids", "wht_pay_type")
    def on_change_tax_ids(self):
        import traceback
        _logger.warning(">>> TRACE [on_change_tax_ids] move_id: %s, _origin: %s\n%s", self.id, self._origin.id if self._origin else None, ''.join(traceback.format_stack()[:-1]))
        """
        สร้าง taxes_line_ids สำหรับแสดงผลยอด WHT บนฟอร์มใบแจ้งหนี้

        ใช้ WHTCalculationService.compute_wht_by_pay_type() เป็น Single Source of Truth
        แทน inline formulas เดิมที่มีตรรกะซ้ำซ้อนและ error-prone
        รองรับทั้งแบบ normal, gross_up_forever และ gross_up_once
        รวมถึง tax-on-tax (WHT คำนวณบน VAT ไม่ใช่บน subtotal)

        PHASE 2 HOTFIX:
        ทุก (0, 0, vals) ต้องส่ง company_id ใน vals อย่างชัดเจน
        เพราะ account.move.tax.lines.company_id เป็น required field
        และ Odoo 18 validate ก่อน compute ทำงาน (race condition)
        """
        if self.env.context.get("skip_wht_recompute"):
            return

        self.taxes_line_ids = [(5, 0, 0)]
        wht_map = {}

        # PHASE 2: คำนวณ company_id ล่วงหน้า — ใช้ self._origin สำหรับ onchange context
        # fallback chain: _origin.company_id → company_id → env.company
        company_id = (
            (self._origin.company_id.id if self._origin and self._origin.company_id else None)
            or (self.company_id.id if self.company_id else None)
            or self.env.company.id
        )

        for line in self.invoice_line_ids:
            if line.wht_tax_ids:
                for rec in line.wht_tax_ids:
                    amount = 0

                    if not rec.is_vat_based_wht():
                        # ── กรณีทั่วไป: WHT คำนวณบน price_subtotal ──
                        try:
                            calc = WHTCalculationService.compute_wht_by_pay_type(
                                line.price_subtotal,
                                rec.amount,
                                self.wht_pay_type or "normal",
                            )
                        except (ValueError, ZeroDivisionError) as e:
                            raise UserError(str(e))
                        amount = calc["wht"]

                    elif (
                        rec.is_vat_based_wht()
                        and rec.sale_tax_id.id in line.tax_ids.ids
                    ):
                        # ── กรณี tax-on-tax: WHT คำนวณบนยอด VAT ──
                        # คำนวณ VAT amount ก่อนเพื่อใช้เป็น base
                        if rec.sale_tax_id.price_include:
                            tax_rate_factor = 1.0 + rec.sale_tax_id.amount / 100.0
                            amount_after_tax = (
                                round(line.price_subtotal / tax_rate_factor, 2)
                                if tax_rate_factor
                                else line.price_subtotal
                            )
                            base_for_wht = line.price_subtotal - amount_after_tax
                        else:
                            base_for_wht = round(
                                line.price_subtotal * (rec.sale_tax_id.amount / 100.0),
                                2,
                            )
                        try:
                            calc = WHTCalculationService.compute_wht_by_pay_type(
                                base_for_wht,
                                rec.amount,
                                self.wht_pay_type or "normal",
                            )
                        except (ValueError, ZeroDivisionError) as e:
                            raise UserError(str(e))
                        amount = calc["wht"]

                    if amount:
                        account_id = (
                            rec.account_id.id
                            if self.move_type in ["in_invoice", "out_refund"]
                            else rec.refund_account_id.id
                        )
                        if rec.id not in wht_map:
                            wht_map[rec.id] = {
                                "name": rec.name,
                                "amount": amount,
                                "account_id": account_id,
                                "wht_tax_id": rec.id,
                                "move_id": self._origin.id or self.id,
                                "company_id": company_id,
                            }
                        else:
                            wht_map[rec.id]["amount"] += amount

        if wht_map:
            self.taxes_line_ids = [
                (0, 0, data) for wht_id, data in wht_map.items()
            ]

    def js_assign_outstanding_line(self, line_id):
        """Called when accountant clicks 'Add' to match an outstanding payment to this bill.
        After reconciliation completes, trigger WHT certificate creation if the bill is now paid.
        NOTE: Certificate creation is now handled by payment.action_post() (payment-centric).
        """
        res = super(AccountMove, self).js_assign_outstanding_line(line_id)
        # Certificate creation moved to payment-centric - remove invoice-centric call
        return res

    @api.depends(
        "line_ids.matched_debit_ids",
        "line_ids.matched_credit_ids",
        "line_ids.reconciled",
    )
    def _compute_payment_state(self):
        super(AccountMove, self)._compute_payment_state()


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    wht_tax_ids = fields.Many2many(
        "account.wht",
        string="WHT",
        compute="_compute_wht_tax_ids",
        store=True,
        readonly=False,
    )
    wht_id = fields.Many2one("account.wht", string="WHT ID")
    wht_rate = fields.Float(string="WHT Rate", related="wht_id.amount", readonly=True)
    wht_amount = fields.Monetary(string="WHT Amount")
    wht_type = fields.Selection(
        related="wht_id.wht_type", string="WHT Type", readonly=True
    )

    is_wht_line = fields.Boolean()
    wht_invoice_ref_id = fields.Many2one("account.move")

    @api.depends("wht_id")
    def _compute_wht_tax_ids(self):
        for line in self:
            if line.wht_id:
                line.wht_tax_ids = [(6, 0, [line.wht_id.id])]
            else:
                line.wht_tax_ids = [(5, 0, 0)]

    @api.onchange("wht_id")
    def _onchange_wht_id(self):
        if self.wht_id:
            self.wht_tax_ids = [(6, 0, [self.wht_id.id])]
        else:
            self.wht_tax_ids = [(5, 0, 0)]
