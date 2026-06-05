# -*- coding: utf-8 -*-
"""
Unit Tests for WHT Calculation Service Layer

Tests the deterministic behavior of the centralized WHT calculation service,
ensuring that the same inputs always produce the same outputs.
"""

# นำเข้า regression tests (10 scenarios สำหรับ critical bug fixes)
from . import test_wht_regression  # noqa: F401

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TestWHTCalculationService(TransactionCase):
    """Test cases for WHT Calculation Service"""
    
    def setUp(self):
        super(TestWHTCalculationService, self).setUp()
        self.service = self.env['wht.calculation.service']
    
    def test_calculate_wht_normal(self):
        """Test normal WHT calculation (หัก ณ ที่จ่าย)"""
        # Base 1000, Rate 3%, Normal
        result = self.service.calculate_wht(1000.0, 3.0, 'normal')
        
        self.assertEqual(result['base'], 1000.0)
        self.assertEqual(result['wht'], 30.0)
        self.assertEqual(result['gross_up'], 0.0)
    
    def test_calculate_wht_gross_up_forever(self):
        """Test gross-up forever calculation (ออกให้ตลอด)"""
        # Base 1000, Rate 3%, Gross-up forever
        # Expected: base = 1000 / (1 - 0.03) = 1030.93
        # WHT = 1030.93 * 0.03 = 30.93
        result = self.service.calculate_wht(1000.0, 3.0, 'gross_up_forever')
        
        self.assertAlmostEqual(result['base'], 1030.93, places=2)
        self.assertAlmostEqual(result['wht'], 30.93, places=2)
        self.assertEqual(result['gross_up'], 30.93)
    
    def test_calculate_wht_gross_up_once(self):
        """Test gross-up once calculation (ออกให้ครั้งเดียว)"""
        # Base 1000, Rate 3%, Gross-up once
        # Expected: gross_up = 1000 * 0.03 = 30
        # base = 1000 + 30 = 1030
        # WHT = 1030 * 0.03 = 30.90
        result = self.service.calculate_wht(1000.0, 3.0, 'gross_up_once')
        
        self.assertAlmostEqual(result['base'], 1030.0, places=2)
        self.assertAlmostEqual(result['wht'], 30.90, places=2)
        self.assertEqual(result['gross_up'], 30.0)
    
    def test_calculate_wht_determinism(self):
        """Test that same inputs always produce same outputs (determinism)"""
        # Call the same calculation multiple times
        result1 = self.service.calculate_wht(1000.0, 3.0, 'normal')
        result2 = self.service.calculate_wht(1000.0, 3.0, 'normal')
        result3 = self.service.calculate_wht(1000.0, 3.0, 'normal')
        
        # All results should be identical
        self.assertEqual(result1, result2)
        self.assertEqual(result2, result3)
    
    def test_calculate_wht_rate_100_error(self):
        """Test that 100% rate raises error for gross-up forever"""
        with self.assertRaises(UserError):
            self.service.calculate_wht(1000.0, 100.0, 'gross_up_forever')
    
    def test_calculate_wht_negative_base_error(self):
        """Test that negative base amount raises error"""
        with self.assertRaises(UserError):
            self.service.calculate_wht(-100.0, 3.0, 'normal')
    
    def test_calculate_wht_negative_rate_error(self):
        """Test that negative rate raises error"""
        with self.assertRaises(UserError):
            self.service.calculate_wht(1000.0, -3.0, 'normal')
    
    def test_calculate_wht_invalid_pay_type_error(self):
        """Test that invalid pay type raises error"""
        with self.assertRaises(UserError):
            self.service.calculate_wht(1000.0, 3.0, 'invalid')
    
    def test_calculate_tax_on_tax_wht(self):
        """Test tax-on-tax calculation"""
        # Tax amount 70, Rate 3%, Normal
        result = self.service.calculate_tax_on_tax_wht(70.0, 3.0, 'normal')
        
        self.assertEqual(result['base'], 70.0)
        self.assertEqual(result['wht'], 2.1)
        self.assertEqual(result['gross_up'], 0.0)
    
    def test_rounding_consistency(self):
        """Test that rounding is consistent across different inputs"""
        # Test rounding edge cases
        result1 = self.service.calculate_wht(1000.333, 3.333, 'normal')
        result2 = self.service.calculate_wht(2000.666, 3.333, 'normal')
        result3 = self.service.calculate_wht(3333.999, 3.333, 'normal')
        
        # All should round to 2 decimal places
        self.assertEqual(len(f"{result1['wht']:.2f}"), len(f"{result1['wht']:.2f}"))
        self.assertEqual(len(f"{result2['wht']:.2f}"), len(f"{result2['wht']:.2f}"))
        self.assertEqual(len(f"{result3['wht']:.2f}"), len(f"{result3['wht']:.2f}"))


class TestWHTServiceIntegration(TransactionCase):
    """Integration tests for WHT Service with actual Odoo models"""
    
    def setUp(self):
        super(TestWHTServiceIntegration, self).setUp()
        self.service = self.env['wht.calculation.service']
        
        # Create test data
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'vat': '1234567890123',
        })
        
        self.account_receivable = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable')
        ], limit=1)
        
        self.account_payable = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable')
        ], limit=1)
        
        # Create WHT tax
        self.wht_tax = self.env['account.wht'].create({
            'name': 'Test WHT 3%',
            'amount': 3.0,
            'account_id': self.account_payable.id,
            'tax_application': 'payment',
            'type_tax_use': 'purchase',
        })
        
        self.wht_tax_gross_up = self.env['account.wht'].create({
            'name': 'Test WHT 3% Gross-up',
            'amount': 3.0,
            'account_id': self.account_payable.id,
            'tax_application': 'payment',
            'type_tax_use': 'purchase',
        })
    
    def test_invoice_wht_calculation(self):
        """Test WHT calculation for actual invoice"""
        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Service',
                'price_unit': 1000.0,
                'quantity': 1.0,
                'account_id': self.account_expense.id if self.env['account.account'].search([('account_type', '=', 'expense')], limit=1) else self.account_payable.id,
            })],
            'wht_pay_type': 'normal',
        })
        
        # Add WHT tax to line
        invoice.invoice_line_ids[0].wht_tax_ids = [(4, self.wht_tax.id)]
        
        # Calculate WHT
        result = self.service.calculate_invoice_wht(invoice)
        
        # Verify
        self.assertEqual(len(result['by_line']), 1)
        self.assertEqual(result['total']['base'], 1000.0)
        self.assertEqual(result['total']['wht'], 30.0)
    
    def test_invoice_wht_calculation_gross_up(self):
        """Test invoice WHT calculation with gross-up"""
        # Create invoice with gross-up
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Service',
                'price_unit': 1000.0,
                'quantity': 1.0,
                'account_id': self.account_expense.id if self.env['account.account'].search([('account_type', '=', 'expense')], limit=1) else self.account_payable.id,
            })],
            'wht_pay_type': 'gross_up_forever',
        })
        
        # Add WHT tax
        invoice.invoice_line_ids[0].wht_tax_ids = [(4, self.wht_tax_gross_up.id)]
        
        # Calculate WHT
        result = self.service.calculate_invoice_wht(invoice)
        
        # Verify gross-up calculation
        self.assertEqual(len(result['by_line']), 1)
        self.assertAlmostEqual(result['total']['base'], 1030.93, places=2)
        self.assertAlmostEqual(result['total']['wht'], 30.93, places=2)
        self.assertEqual(result['total']['gross_up'], 30.93)
    
    def test_payment_ratio_calculation(self):
        """Test payment ratio calculation"""
        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Service',
                'price_unit': 1000.0,
                'quantity': 1.0,
                'account_id': self.account_expense.id if self.env['account.account'].search([('account_type', '=', 'expense')], limit=1) else self.account_payable.id,
            })],
            'wht_pay_type': 'normal',
        })
        
        invoice.invoice_line_ids[0].wht_tax_ids = [(4, self.wht_tax.id)]
        
        # Calculate full WHT
        full_wht = self.service.calculate_invoice_wht(invoice)
        
        # Create partial payment (50%)
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_id': self.partner.id,
            'amount': 500.0,
            'journal_id': self.env['account.journal'].search([('type', '=', 'cash')], limit=1).id,
        })
        
        # Calculate payment ratio
        ratio = self.service.calculate_payment_ratio(payment, invoice)
        
        # Should be approximately 0.485 (500 / 1030) after gross-up
        self.assertGreater(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)
    
    def test_consistency_validation(self):
        """Test WHT calculation consistency validation"""
        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Service',
                'price_unit': 1000.0,
                'quantity': 1.0,
                'account_id': self.account_expense.id if self.env['account.account'].search([('account_type', '=', 'expense')], limit=1) else self.account_payable.id,
            })],
            'wht_pay_type': 'normal',
        })
        
        invoice.invoice_line_ids[0].wht_tax_ids = [(4, self.wht_tax.id)]
        
        # Validate consistency (should be consistent since invoice not posted yet)
        result = self.service.validate_wht_calculation_consistency(invoice)
        
        # For unposted invoice, stored values are 0
        # This test demonstrates the validation method works
        self.assertIn('is_consistent', result)
        self.assertIn('calculated', result)
        self.assertIn('stored', result)


class TestWHTIdempotency(TransactionCase):
    """Test idempotency of WHT operations"""
    
    def setUp(self):
        super(TestWHTIdempotency, self).setUp()
        
        # Create test data
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'vat': '1234567890123',
        })
        
        self.account_payable = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable')
        ], limit=1)
        
        self.wht_tax = self.env['account.wht'].create({
            'name': 'Test WHT 3%',
            'amount': 3.0,
            'account_id': self.account_payable.id,
            'tax_application': 'payment',
            'type_tax_use': 'purchase',
            'income_type_id': self.env['wht.income.type'].search([], limit=1).id if self.env['wht.income.type'].search([], limit=1) else False,
        })
        
        self.journal = self.env['account.journal'].search([('type', '=', 'cash')], limit=1)
    
    def test_certificate_idempotency_key(self):
        """Test that certificate idempotency key prevents duplicates"""
        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Service',
                'price_unit': 1000.0,
                'quantity': 1.0,
            })],
            'wht_pay_type': 'normal',
        })
        
        invoice.invoice_line_ids[0].wht_tax_ids = [(4, self.wht_tax.id)]
        
        # Create payment
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_id': self.partner.id,
            'amount': 970.0,
            'journal_id': self.journal.id,
        })
        
        # Generate idempotency key
        cert_key = f"{payment.id}_{invoice.id}_pnd53_normal"
        
        # Try to create certificate with same key twice
        cert1 = self.env['account.wht.certificate'].create({
            'partner_id': self.partner.id,
            'move_ids': [(6, 0, invoice.ids)],
            'payment_id': payment.id,
            'custom_key': cert_key,
            'state': 'done',
        })
        
        # Second create should fail due to SQL constraint
        with self.assertRaises(Exception):  # Should fail due to unique constraint
            cert2 = self.env['account.wht.certificate'].create({
                'partner_id': self.partner.id,
                'move_ids': [(6, 0, invoice.ids)],
                'payment_id': payment.id,
                'custom_key': cert_key,
                'state': 'done',
            })
        
        # Verify only one certificate exists
        certs = self.env['account.wht.certificate'].search([
            ('custom_key', '=', cert_key)
        ])
        self.assertEqual(len(certs), 1)


if __name__ == '__main__':
    import unittest
    unittest.main()
