# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _create_wht_certificate_after_payment_creation(self):
        """
        Payment-Centric WHT Certificate Creation (Production-Grade).

        Architecture:
        - PRIMARY bill source: wizard.line_ids.mapped('move_id') — reliable even without
          active_ids forwarding, because the wizard record still lives in the same request.
        - Fallback: context active_ids (for custom callers that set it explicitly).
        - Snapshots all partner/bill metadata at creation time so legal records never
          drift when master data changes later.
        - Multi-bill safe: each detail line carries invoice_move_id for traceability.
        - Idempotent: safe to retry; duplicate check runs before any write.
        - NEVER raises — WHT failure must not roll back the payment.
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
        # wht_all_payment_ids is injected by _create_payments() when the wizard
        # produces multiple payments (non-grouped flow).  Checking ALL IDs prevents
        # duplicate certs when the same wizard is retried after a partial failure.
        _all_payment_ids = list(self.env.context.get('wht_all_payment_ids') or [self.id])
        existing = self.env['account.wht.certificate'].search([
            ('payment_id', 'in', _all_payment_ids),
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
            # STEP 1 ── Discover source bills ──────────────────────────────────
            invoices = self.env['account.move']

            # Primary: wizard.line_ids are the move lines being registered.
            # .mapped('move_id') gives the actual vendor bills.
            if hasattr(wizard, 'line_ids') and wizard.line_ids:
                invoices = wizard.line_ids.mapped('move_id').filtered(
                    lambda m: m.move_type in (
                        'in_invoice', 'out_invoice', 'in_refund', 'out_refund'
                    ) and m.state == 'posted'
                )
                _logger.info("[WHT BILLS] %d bill(s) via wizard.line_ids for payment %s",
                             len(invoices), self.name)

            # Fallback: context active_ids (custom callers / edge cases)
            if not invoices:
                active_ids = self.env.context.get('active_ids', [])
                active_model = self.env.context.get('active_model', '')
                if active_ids:
                    if active_model == 'account.move.line':
                        move_lines = self.env['account.move.line'].browse(active_ids).exists()
                        invoices = move_lines.mapped('move_id').filtered(
                            lambda m: m.move_type in (
                                'in_invoice', 'out_invoice', 'in_refund', 'out_refund'
                            )
                        )
                    else:
                        invoices = self.env['account.move'].browse(active_ids).filtered(
                            lambda m: m.move_type in (
                                'in_invoice', 'out_invoice', 'in_refund', 'out_refund'
                            )
                        )
                    if invoices:
                        _logger.info(
                            "[WHT BILLS] %d bill(s) via context.active_ids (fallback) for payment %s",
                            len(invoices), self.name,
                        )

            if not invoices:
                _logger.warning(
                    "[WHT WARN] No source bills found for payment %s — "
                    "certificate will be created without bill linkage",
                    self.name,
                )

            # STEP 2 ── Snapshot partner metadata ─────────────────────────────
            partner = self.partner_id
            partner_name_snapshot = partner.name or '' if partner else ''
            partner_taxid_snapshot = partner.vat or '' if partner else ''
            partner_address_snapshot = ''
            if partner:
                try:
                    partner_address_snapshot = partner._display_address(
                        without_company=True
                    )
                except Exception:
                    partner_address_snapshot = ', '.join(filter(None, [
                        partner.street, partner.street2,
                        partner.city,
                        partner.state_id.name if partner.state_id else '',
                        partner.zip,
                        partner.country_id.name if partner.country_id else '',
                    ]))

            # STEP 3 ── Snapshot bill metadata ────────────────────────────────
            bill_names = sorted(
                inv.name for inv in invoices
                if inv.name and inv.name not in ('New', '/', False)
            )
            bill_reference_snapshot = ', '.join(bill_names) if bill_names                 else (self.ref or self.name or '')

            invoice_dates = sorted(
                inv.invoice_date for inv in invoices if inv.invoice_date
            )
            invoice_date_snapshot = invoice_dates[0] if invoice_dates else self.date

            branch_snapshot = self.env.company.name or ''

            # STEP 4 ── Build detail lines ─────────────────────────────────────
            lines_vals = self._build_wht_certificate_detail_lines(wizard, invoices)

            # STEP 5 ── Source traceability (invoice line IDs) ─────────────────
            source_line_ids = []
            for inv in invoices:
                source_line_ids.extend(inv.invoice_line_ids.ids)

            # STEP 6 ── Assemble certificate values ───────────────────────────
            cert_vals = {
                # Core
                'payment_id':  self.id,
                'partner_id':  partner.id if partner else False,
                'issue_date':  self.date,
                'pay_date':    self.date,
                'wht_type':    wizard.wht_type or 'pnd53',
                'wht_pay_type': wizard.wht_pay_type or 'normal',
                'state':       'draft',
                # Partner metadata — snapshot values set explicitly (no onchange in ORM)
                'partner_taxid':    partner_taxid_snapshot,
                'partner_address':  partner_address_snapshot,
                # Immutable historical snapshots
                'partner_name_snapshot':  partner_name_snapshot,
                'bill_reference_snapshot': bill_reference_snapshot,
                'branch_snapshot':        branch_snapshot,
                'invoice_date_snapshot':  invoice_date_snapshot,
                # Reference field for display / report
                'wht_reference': bill_reference_snapshot,
                # Detail lines
                'line_ids': lines_vals,
            }

            if invoices:
                cert_vals['move_ids'] = [(6, 0, invoices.ids)]
            if source_line_ids:
                cert_vals['source_move_line_ids'] = [(6, 0, source_line_ids)]

            # STEP 7 ── Create + confirm ───────────────────────────────────────
            _logger.info(
                "[WHT CERT] Creating certificate: partner=%s, bills=%s, lines=%d",
                partner_name_snapshot, bill_reference_snapshot, len(lines_vals),
            )
            certificate = self.env['account.wht.certificate'].create(cert_vals)
            certificate.action_confirm()
            _logger.info(
                "[WHT CERT] Created and confirmed %s for payment %s",
                certificate.certificate_no, self.name,
            )

        except Exception as e:
            _logger.exception(
                "[WHT ERROR] Failed to create WHT certificate for payment %s: %s",
                self.name or self.id, str(e),
            )
            # CRITICAL: never re-raise — payment must succeed regardless

    def _build_wht_certificate_detail_lines(self, wizard, invoices):
        """
        Build WHT certificate detail lines from wizard WHT lines + source bills.

        Strategy
        --------
        * wizard.wht_line_ids is the authoritative source for **amounts**
          (already computed by the register wizard, including partial-payment scaling).
        * Bills are used only for **traceability** (invoice_move_id on each line).
        * For multi-bill payments the first bill that carries the same WHT is used;
          for single-bill payments the bill is always linked.
        * Lines are ordered to match wizard line order (no surprise reordering).

        Returns list of ORM command tuples: [(0, 0, vals), ...]
        """
        if not wizard or not wizard.wht_line_ids:
            return []

        # Build {wht_id: [invoice, ...]} for source traceability
        bill_wht_map = {}
        for inv in sorted(invoices, key=lambda x: (x.invoice_date or '', x.name or '', x.id)):
            for line in sorted(inv.invoice_line_ids, key=lambda x: x.sequence):
                for wht in self._get_wht_taxes_from_invoice_line(line):
                    bill_wht_map.setdefault(wht.id, [])
                    if inv not in bill_wht_map[wht.id]:
                        bill_wht_map[wht.id].append(inv)

        lines_vals = []
        for w_line in wizard.wht_line_ids:
            wht = w_line.wht_id

            # Best-effort: link to the first bill that carries this WHT tax
            source_bills = bill_wht_map.get(wht.id, []) if wht else []
            if not source_bills and len(invoices) == 1:
                source_bills = list(invoices)
            source_invoice = source_bills[0] if source_bills else False

            lines_vals.append((0, 0, {
                'income_type_id': wht.income_type_id.id if wht and wht.income_type_id else False,
                'name':           w_line.name or (wht.name if wht else ''),
                'base_amount':    w_line.base_amount,
                'tax_amount':     w_line.amount,
                'wht_pay_type':   wizard.wht_pay_type or 'normal',
                'pay_date':       self.date,
                'invoice_move_id': source_invoice.id if source_invoice else False,
            }))

        return lines_vals

    def _get_wht_taxes_from_invoice_line(self, line):
        """
        Return list of account.wht records linked to an invoice line.

        Supports two integration styles used by this module:
        1. Direct wht_tax_ids field (preferred — direct Many2many on invoice line).
        2. Lookup through tax_ids against account.wht.sale_tax_id (legacy style).
        """
        if not line:
            return []

        # Style 1 – direct wht_tax_ids field
        if 'wht_tax_ids' in line._fields and line.wht_tax_ids:
            return list(line.wht_tax_ids)

        # Style 2 – lookup account.wht by matching sale_tax_id
        if line.tax_ids:
            all_wht = self.env['account.wht'].search(
                [('tax_application', '=', 'payment')]
            )
            wht_by_tax = {w.sale_tax_id.id: w for w in all_wht if w.sale_tax_id}
            return [wht_by_tax[t.id] for t in line.tax_ids if t.id in wht_by_tax]

        return []

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
                ("payment_id", "=", payment.id),
                ("state", "!=", "cancel"),
            ])

    def action_view_wht_certificates(self):
        self.ensure_one()
        return {
            "name": _("WHT Certificates"),
            "type": "ir.actions.act_window",
            "res_model": "account.wht.certificate",
            "view_mode": "list,form",
            "domain": [("payment_id", "=", self.id), ("state", "!=", "cancel")],
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
        # WHT amounts on payment are computed via account.payment.register (wizard).
        # Direct computation from invoices is handled during the payment registration
        # workflow. Here we ensure the stored fields always have a valid default.
        for payment in self:
            payment.wht_amount = 0.00
            payment.after_wh_payment_amount = payment.amount
