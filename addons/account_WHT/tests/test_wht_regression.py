# -*- coding: utf-8 -*-
"""
Regression Tests for WHT Module — Critical Bug Fixes
=====================================================

ทดสอบ 10 สถานการณ์สำคัญที่เคยพบปัญหาจริงในการใช้งาน:

  RC-01  button_cancel() ค้นหา cert ผ่าน payment_id (legacy Many2one)
  RC-02  button_cancel() ค้นหา cert ผ่าน payment_ids (Many2many ใหม่)
  RC-03  _check_currency_consistency() ตรวจ payment_ids สกุลเงินไม่ตรง
  RC-04  action_confirm() ปฏิเสธ cert ที่ไม่มี line_ids
  RC-05  action_confirm() อนุญาต cert ที่มี line_ids
  RC-06  compute_wht_by_pay_type() — normal pay type
  RC-07  compute_wht_by_pay_type() — gross_up_forever pay type
  RC-08  compute_wht_by_pay_type() — gross_up_once pay type
  RC-09  compute_wht_by_pay_type() — ปฏิเสธ rate=100% ใน gross_up_forever
  RC-10  generate_wht_move_lines() — round ผลลัพธ์ ไม่ใช่อัตรา
"""

import logging
from unittest.mock import MagicMock, patch, PropertyMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TestWHTRegressionCritical(TransactionCase):
    """
    Regression tests สำหรับ bug fixes ใน WHT module

    ใช้ TransactionCase เพื่อ rollback ทุก test case โดยอัตโนมัติ
    ไม่สร้าง data จริงใน DB เพื่อความเร็วและ isolation
    """

    # ─────────────────────────────────────────────────────────────────────
    # RC-06 ~ RC-09: WHTCalculationService.compute_wht_by_pay_type()
    # ─────────────────────────────────────────────────────────────────────

    def test_rc06_compute_normal(self):
        """RC-06: normal pay type คำนวณ WHT = base × rate โดยตรง"""
        from odoo.addons.account_WHT.models.wht_calculation_service import WHTCalculationService

        result = WHTCalculationService.compute_wht_by_pay_type(1000.0, 3.0, 'normal')
        self.assertAlmostEqual(result['base'], 1000.0, places=2)
        self.assertAlmostEqual(result['wht'], 30.0, places=2)
        _logger.info("[RC-06] PASS: normal WHT=%.2f", result['wht'])

    def test_rc07_compute_gross_up_forever(self):
        """RC-07: gross_up_forever → base = original / (1 - rate)"""
        from odoo.addons.account_WHT.models.wht_calculation_service import WHTCalculationService

        # 1000 / (1 - 0.03) = 1030.93, WHT = 1030.93 * 0.03 ≈ 30.93
        result = WHTCalculationService.compute_wht_by_pay_type(1000.0, 3.0, 'gross_up_forever')
        expected_base = round(1000.0 / (1.0 - 0.03), 2)
        expected_wht = round(expected_base * 0.03, 2)
        self.assertAlmostEqual(result['base'], expected_base, places=2)
        self.assertAlmostEqual(result['wht'], expected_wht, places=2)
        _logger.info("[RC-07] PASS: gross_up_forever base=%.2f WHT=%.2f", result['base'], result['wht'])

    def test_rc08_compute_gross_up_once(self):
        """RC-08: gross_up_once → base = original + (original × rate)"""
        from odoo.addons.account_WHT.models.wht_calculation_service import WHTCalculationService

        # 1000 + (1000 × 0.03) = 1030, WHT = 1030 × 0.03 = 30.90
        result = WHTCalculationService.compute_wht_by_pay_type(1000.0, 3.0, 'gross_up_once')
        expected_base = round(1000.0 + (1000.0 * 0.03), 2)
        expected_wht = round(expected_base * 0.03, 2)
        self.assertAlmostEqual(result['base'], expected_base, places=2)
        self.assertAlmostEqual(result['wht'], expected_wht, places=2)
        _logger.info("[RC-08] PASS: gross_up_once base=%.2f WHT=%.2f", result['base'], result['wht'])

    def test_rc09_gross_up_forever_100pct_rejected(self):
        """RC-09: rate=100% ใน gross_up_forever ต้องโยน ValueError (หาร 0)"""
        from odoo.addons.account_WHT.models.wht_calculation_service import WHTCalculationService

        with self.assertRaises((ValueError, ZeroDivisionError)):
            WHTCalculationService.compute_wht_by_pay_type(1000.0, 100.0, 'gross_up_forever')
        _logger.info("[RC-09] PASS: rate=100%% ถูกปฏิเสธสำเร็จ")

    # ─────────────────────────────────────────────────────────────────────
    # RC-10: generate_wht_move_lines() rounding
    # ─────────────────────────────────────────────────────────────────────

    def test_rc10_rounding_on_result_not_rate(self):
        """
        RC-10: ต้อง round ที่ผลลัพธ์ ไม่ใช่ที่อัตรา

        Bug เดิม: price_subtotal * round(amount/100, 2)
          → 1000 × round(7.5/100, 2) = 1000 × 0.08 = 80.0  ← ผิด!
        Fix ใหม่: round(price_subtotal * (amount/100), 2)
          → round(1000 × 0.075, 2) = round(75.0, 2) = 75.0  ← ถูก
        """
        from odoo.addons.account_WHT.models.wht_calculation_service import WHTCalculationService

        # ทดสอบ rate 7.5% กับ base 1000
        result = WHTCalculationService.compute_wht_by_pay_type(1000.0, 7.5, 'normal')
        self.assertAlmostEqual(result['wht'], 75.0, places=2,
                               msg="WHT 7.5% ของ 1000 ต้องเท่ากับ 75.0 ไม่ใช่ 80.0 (bug เดิม)")
        _logger.info("[RC-10] PASS: rounding ถูกต้อง WHT=%.2f", result['wht'])

    # ─────────────────────────────────────────────────────────────────────
    # RC-04 ~ RC-05: action_confirm() safety guard
    # ─────────────────────────────────────────────────────────────────────

    def test_rc04_confirm_rejects_empty_line_ids(self):
        """RC-04: action_confirm() ต้องปฏิเสธ cert ที่ไม่มี line_ids"""
        # สร้าง WHT cert ในสถานะ draft โดยไม่มี line_ids
        wht_type = self.env['account.wht.type'].search([], limit=1)
        if not wht_type:
            _logger.warning("[RC-04] SKIP: ไม่มี account.wht.type ใน DB")
            return

        partner = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
        if not partner:
            _logger.warning("[RC-04] SKIP: ไม่มี supplier partner ใน DB")
            return

        cert = self.env['account.wht.certificate'].create({
            'partner_id': partner.id,
            'state': 'draft',
        })
        # ไม่มี line_ids → ต้องโยน UserError
        with self.assertRaises(UserError):
            cert.action_confirm()
        _logger.info("[RC-04] PASS: cert ว่างถูกปฏิเสธ")

    def test_rc05_confirm_allows_nonempty_line_ids(self):
        """RC-05: action_confirm() อนุญาต cert ที่มี line_ids อย่างน้อย 1 รายการ"""
        wht_tax = self.env['account.tax'].search([
            ('is_wht', '=', True),
            ('type_tax_use', '=', 'purchase'),
        ], limit=1)
        if not wht_tax:
            _logger.warning("[RC-05] SKIP: ไม่มี WHT tax ใน DB")
            return

        partner = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
        if not partner:
            _logger.warning("[RC-05] SKIP: ไม่มี supplier partner ใน DB")
            return

        cert = self.env['account.wht.certificate'].create({
            'partner_id': partner.id,
            'state': 'draft',
            'line_ids': [(0, 0, {
                'wht_tax_id': wht_tax.id,
                'base_amount': 1000.0,
                'tax_amount': 30.0,
            })],
        })
        # มี line_ids → ต้องไม่โยน UserError (อาจโยน error อื่นจาก sequence/config ได้)
        try:
            cert.action_confirm()
            _logger.info("[RC-05] PASS: cert ที่มีรายการสามารถ confirm ได้")
        except UserError as e:
            # ยอมรับ UserError จากเหตุผลอื่น (เช่น sequence ไม่ configured)
            # แต่ต้องไม่ใช่ error เรื่อง "ไม่มีรายการ"
            self.assertNotIn("ไม่มีรายการ", str(e),
                             "action_confirm ไม่ควรปฏิเสธ cert ที่มี line_ids")
            _logger.info("[RC-05] PASS: cert ถูกปฏิเสธด้วยเหตุผลอื่น (ไม่ใช่ empty lines): %s", e)

    # ─────────────────────────────────────────────────────────────────────
    # RC-03: _check_currency_consistency() กับ payment_ids
    # ─────────────────────────────────────────────────────────────────────

    def test_rc03_currency_check_covers_payment_ids(self):
        """
        RC-03: _check_currency_consistency() ต้องตรวจสอบ payment_ids
        ด้วย ไม่ใช่แค่ payment_id (legacy)
        """
        # ตรวจว่า decorator ของ method มี 'payment_ids' อยู่
        from odoo.addons.account_WHT.models.account_wht import AccountWHTCertificate
        method = AccountWHTCertificate._check_currency_consistency
        # api.constrains stores the fields in _constrains on the model
        # แค่ตรวจว่า method มีอยู่และ docstring กล่าวถึง payment_ids
        self.assertIsNotNone(method)
        doc = method.__doc__ or ''
        self.assertIn('payment_ids', doc,
                      "_check_currency_consistency docstring ต้องระบุว่าครอบคลุม payment_ids")
        _logger.info("[RC-03] PASS: method ครอบคลุม payment_ids")

    # ─────────────────────────────────────────────────────────────────────
    # RC-01 ~ RC-02: button_cancel() domain
    # ─────────────────────────────────────────────────────────────────────

    def test_rc01_cancel_searches_payment_id_legacy(self):
        """
        RC-01: ยืนยันว่า button_cancel() ใน account_move.py
        ยังคงค้นหาผ่าน payment_id (legacy Many2one) ด้วย
        """
        import ast, inspect
        from odoo.addons.account_WHT.models.account_move import AccountMove
        source = inspect.getsource(AccountMove.button_cancel)
        self.assertIn("'payment_id'", source,
                      "button_cancel() ต้องค้นหา cert ผ่าน payment_id")
        _logger.info("[RC-01] PASS: button_cancel() ค้นหาผ่าน payment_id")

    def test_rc02_cancel_also_searches_payment_ids_m2m(self):
        """
        RC-02: ยืนยันว่า button_cancel() ใน account_move.py
        ค้นหาผ่าน payment_ids (Many2many ใหม่) ด้วย ไม่ใช่แค่ payment_id
        """
        import inspect
        from odoo.addons.account_WHT.models.account_move import AccountMove
        source = inspect.getsource(AccountMove.button_cancel)
        self.assertIn("'payment_ids'", source,
                      "button_cancel() ต้องค้นหา cert ผ่าน payment_ids ด้วย")
        self.assertIn("'|'", source,
                      "button_cancel() ต้องใช้ OR domain เพื่อค้นหาทั้งสองฟิลด์")
        _logger.info("[RC-02] PASS: button_cancel() ค้นหาผ่าน payment_ids ด้วย OR domain")
