# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, Command
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_cancel(self):
        res = super(AccountPayment, self).action_cancel()
        for payment in self:
            certs = self.env['account.wht.certificate'].search([
                ('payment_id', '=', payment.id),
                ('state', '!=', 'cancel')
            ])
            if certs:
                certs.action_cancel()
        return res

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        # Trigger WHT certificate creation for all bills reconciled during this posting.
        # This covers the "Register Payment from Bill" flow.
        for payment in self:
            if payment.payment_type == 'outbound':
                bills = payment.reconciled_bill_ids
                if bills:
                    bills._create_wht_certificate_if_needed()
        return res

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
            payment.wht_certificate_count = self.env[
                "account.wht.certificate"
            ].search_count([("payment_id", "=", payment.id)])

    def action_view_wht_certificates(self):
        self.ensure_one()
        return {
            "name": _("WHT Certificates"),
            "type": "ir.actions.act_window",
            "res_model": "account.wht.certificate",
            "view_mode": "list,form",
            "domain": [("payment_id", "=", self.id)],
            "context": {
                "default_payment_id": self.id,
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
        """ Calculate the ratio of payment to the invoices' net total. """
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
        for payment in self:
            final_amount = 0.00
            invoices = False
            if payment.reconciled_bill_ids:
                invoices = payment.reconciled_bill_ids
            if payment.reconciled_invoice_ids:
                invoices = payment.reconciled_invoice_ids
            if invoices:
                percentage = self._get_wht_payment_ratio(payment, invoices)
                for invoice in invoices:
                    if invoice:
                        if payment.override_wht and payment.wht_ids:
                            for wht in payment.wht_ids:
                                if wht.type_tax_use != "tax" and wht.amount:
                                    wht_amount = round(
                                        payment.amount * (wht.amount / 100), 2
                                    )
                                    final_amount += wht_amount
                                if wht.type_tax_use == "tax":
                                    tax_amount = round(
                                        invoice.amount_untaxed
                                        * (wht.sale_tax_id.amount / 100),
                                        2,
                                    )
                                    wht_amount = round(
                                        tax_amount * (wht.amount / 100), 2
                                    )
                                    final_amount += wht_amount
                        else:
                            for line in invoice.invoice_line_ids.filtered(
                                lambda l: l.wht_tax_ids
                            ):
                                for wht in line.wht_tax_ids.filtered(
                                    lambda w: w.tax_application == "payment"
                                ):
                                    if wht.type_tax_use != "tax" and wht.amount:
                                        rate = wht.amount / 100.0
                                        pay_type = getattr(invoice, 'wht_pay_type', 'normal')
                                        if pay_type == 'gross_up_forever':
                                            if abs(1 - rate) < 1e-9:
                                                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % wht.name)
                                            base = line.price_subtotal / (1 - rate)
                                        elif pay_type == 'gross_up_once':
                                            base = line.price_subtotal * (1 + rate)
                                        else:
                                            base = line.price_subtotal
                                            
                                        wht_amount = round(base * rate, 2)
                                        wht_amount_ded = round(
                                            wht_amount * percentage, 2
                                        )
                                        final_amount += wht_amount_ded

                                    if (
                                        wht.type_tax_use == "tax"
                                        and wht.sale_tax_id.id in line.tax_ids.ids
                                    ):
                                        if wht.sale_tax_id.price_include:
                                            amount_after_tax = round(
                                                line.price_subtotal
                                                / (1 + wht.sale_tax_id.amount / 100),
                                                2,
                                            )
                                            tax_amount = (
                                                line.price_subtotal - amount_after_tax
                                            )
                                        else:
                                            tax_amount = round(
                                                line.price_subtotal
                                                * (wht.sale_tax_id.amount / 100),
                                                2,
                                            )
                                        wht_amount = round(
                                            tax_amount * (wht.amount / 100), 2
                                        )
                                        wht_amount_ded = round(
                                            wht_amount * percentage, 2
                                        )
                                        final_amount += wht_amount_ded

                    else:
                        if payment.move_id:
                            for wht in self.wht_ids:
                                if wht.type_tax_use != "tax" and wht.amount:
                                    # Use amount_untaxed for pre-VAT base
                                    wht_amount = round(
                                        payment.move_id.amount_untaxed * (wht.amount / 100), 2
                                    )
                                    final_amount += wht_amount

            payment.wht_amount = final_amount
            # Use payment.amount instead of payment_amount to avoid zero value issues in form view
            payment.after_wh_payment_amount = payment.amount - payment.wht_amount

            if not final_amount:
                payment.wht_amount = 0.00
                payment.after_wh_payment_amount = payment.amount

    def generate_lines(self, payment, wht_amount_ded, res, wht, inv=False):
        company_currency = payment.company_id.currency_id
        payment_currency = payment.currency_id
        if payment_currency == company_currency:
            wht_amount_company = wht_amount_ded
        else:
            wht_amount_company = payment_currency._convert(
                wht_amount_ded, company_currency, payment.company_id, payment.date
            )
        debit = 0.0
        credit = 0.0
        wht_names = set(self.env["account.wht"].search([]).mapped("name"))
        if wht_amount_company and payment.payment_type == "outbound":
            for line in res:
                if (
                    line["credit"] != 0.0
                    and "Write-Off" not in line["name"]
                    and line["name"]
                    not in wht_names
                ):
                    line["credit"] = round(line["credit"] - wht_amount_company, 2)
                    if payment_currency != company_currency and "amount_currency" in line:
                        line["amount_currency"] = round(line["amount_currency"] + wht_amount_ded, 2)

            debit = 0.0
            credit = wht_amount_company
        elif wht_amount_company and payment.payment_type == "inbound":
            for line in res:
                if (
                    line["debit"] != 0.0
                    and "Write-Off" not in line["name"]
                    and line["account_id"] not in [wht.account_id.id]
                ):
                    line["debit"] = round(line["debit"] - wht_amount_company, 2)
                    if payment_currency != company_currency and "amount_currency" in line:
                        line["amount_currency"] = round(line["amount_currency"] - wht_amount_ded, 2)

            debit = wht_amount_company
            credit = 0.0

        if debit or credit:
            res.append(
                {
                    "name": wht.name,
                    "currency_id": payment_currency.id,
                    "debit": debit,
                    "credit": credit,
                    "amount_currency": wht_amount_ded if debit > 0 else -wht_amount_ded,
                    "date_maturity": payment.date,
                    "partner_id": payment.partner_id.commercial_partner_id.id,
                    "account_id": wht.account_id.id,
                }
            )

        if inv and inv.move_type in [
            "out_invoice",
            "in_refund",
            "in_invoice",
            "out_refund",
        ]:
            inv.wht_line_ids.create(
                {
                    "name": "Withholding Tax",
                    "account_id": wht.account_id.id,
                    "amount": wht_amount_ded,
                    "move_id": inv.id,
                }
            )

    def _generate_journal_entry(
        self, write_off_line_vals=None, force_balance=None, line_ids=None
    ):
        need_move = self.filtered(lambda p: not p.move_id and p.outstanding_account_id)
        assert len(self) == 1 or (
            not write_off_line_vals and not force_balance and not line_ids
        )

        move_vals = []
        for pay in need_move:
            move_vals.append(
                {
                    "move_type": "entry",
                    "ref": pay.memo,
                    "date": pay.date,
                    "journal_id": pay.journal_id.id,
                    "company_id": pay.company_id.id,
                    "partner_id": pay.partner_id.id,
                    "currency_id": pay.currency_id.id,
                    "partner_bank_id": pay.partner_bank_id.id,
                    "line_ids": line_ids
                    or [
                        Command.create(line_vals)
                        for line_vals in pay._prepare_move_line_default_vals(
                            write_off_line_vals=write_off_line_vals,
                            force_balance=force_balance,
                        )
                    ],
                    "origin_payment_id": pay.id,
                }
            )
        if (
            "wh_created" not in self.env.context.get("params", {})
            or "wh_created" not in self.env.context
        ):
            for i, pay in enumerate(need_move):
                if pay.memo:
                    related_inv = self.env["account.move"].search([("name", "=", pay.memo)])

                    if related_inv:
                        wh_amount = self.env["account.move.tax.lines"].search(
                            [("move_id", "in", related_inv.ids)]
                        )
                        if wh_amount and move_vals and len(move_vals[i]["line_ids"]) > 1:
                            # Safe dynamic lookup: find the largest credit line instead of
                            # hardcoding index [1][2], which fails when tax/discount lines exist
                            credit_line = None
                            for line_tuple in move_vals[i]["line_ids"]:
                                vals = line_tuple[2] if isinstance(line_tuple, (list, tuple)) and len(line_tuple) > 2 else line_tuple
                                if vals.get("credit", 0.0) > 0.0:
                                    if credit_line is None or vals["credit"] > credit_line["credit"]:
                                        credit_line = vals
                            if credit_line:
                                total_wh_amount = sum(wh_amount.mapped("amount"))
                                debit_amount = round(
                                    credit_line["credit"] - total_wh_amount, 2
                                )
                                if debit_amount:
                                    # Only adjust the FIRST debit line (payable) to maintain balance
                                    adjusted = False
                                    for inv in move_vals[i]["line_ids"]:
                                        vals = inv[2] if isinstance(inv, (list, tuple)) and len(inv) > 2 else inv
                                        if vals.get("debit", 0.0) > 0.0 and not adjusted:
                                            vals["debit"] = debit_amount
                                            vals["amount_currency"] = debit_amount
                                            adjusted = True
                                    first_line = move_vals[i]["line_ids"][0]
                                    first_vals = first_line[2] if isinstance(first_line, (list, tuple)) and len(first_line) > 2 else first_line
                                    
                                    for wh_line in wh_amount:
                                        move_vals[i]["line_ids"].append(
                                            (
                                                Command.CREATE,
                                                0,
                                                {
                                                    "account_id": wh_line.account_id.id,
                                                    "amount_currency": wh_line.amount,
                                                    "credit": 0.0,
                                                    "currency_id": self.env.company.currency_id.id,
                                                    "date_maturity": first_vals.get("date_maturity"),
                                                    "debit": wh_line.amount,
                                                    "name": wh_line.name or wh_line.display_name,
                                                    "partner_id": first_vals.get("partner_id"),
                                                },
                                            )
                                        )

            # If 'params' exists in the context, update it
            if "params" in self.env.context:
                params = self.env.context["params"].copy()
                params["wh_created"] = True
                # Create a new environment with updated context
                self = self.with_context(params=params)

            # If 'wh_created' doesn't exist as an attribute, add it to the new context
            if "wh_created" not in self.env.context:
                self = self.with_context(wh_created=True)
        moves = self.env["account.move"].create(move_vals)
        for pay, move in zip(need_move, moves):
            pay.write({"move_id": move.id, "state": "in_process"})
