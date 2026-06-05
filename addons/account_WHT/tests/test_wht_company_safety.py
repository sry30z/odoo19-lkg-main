# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import Command

class TestWhtCompanySafety(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        # Set up a new company to test multi-company environment
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})
        
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
            'company_id': False,
        })
        
        # Accounts
        cls.account_expense = cls.env['account.account'].create({
            'name': 'Expense',
            'code': 'EXP01',
            'account_type': 'expense',
            'company_id': cls.company_a.id,
        })
        
        cls.account_wht = cls.env['account.account'].create({
            'name': 'WHT Liability',
            'code': 'WHT01',
            'account_type': 'liability_current',
            'company_id': cls.company_a.id,
        })

        # Set up a WHT configuration
        cls.wht_tax = cls.env['account.wht'].create({
            'name': 'WHT 3%',
            'amount': 3.0,
            'wht_type': 'pnd3',
            'account_id': cls.account_wht.id,
            'company_id': cls.company_a.id,
        })

    def test_create_account_move_tax_lines_without_company_id(self):
        """ Test that creating account.move.tax.lines without company_id falls back safely """
        # Create a move for company A
        move = self.env['account.move'].with_company(self.company_a).create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company_a.id,
            'invoice_date': '2026-06-01',
        })
        
        # Intentionally create tax line without company_id
        # The safety net should catch it and set it to company_a based on move_id
        tax_line = self.env['account.move.tax.lines'].create({
            'name': 'Tax Line Test',
            'wht_tax_id': self.wht_tax.id,
            'account_id': self.account_wht.id,
            'amount': 30.0,
            'move_id': move.id,
        })
        
        self.assertEqual(tax_line.company_id.id, self.company_a.id, "company_id should be auto-populated from move_id")

    def test_create_account_move_wht_without_company_id(self):
        """ Test that creating account.move.wht without company_id falls back safely """
        move = self.env['account.move'].with_company(self.company_b).create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company_b.id,
            'invoice_date': '2026-06-01',
        })
        
        wht_line = self.env['account.move.wht'].create({
            'name': 'WHT Line Test',
            'account_id': self.account_wht.id,
            'amount': 30.0,
            'move_id': move.id,
        })
        
        self.assertEqual(wht_line.company_id.id, self.company_b.id, "company_id should be auto-populated from move_id")

    def test_api_batch_create_with_missing_company_id(self):
        """ Test creating move with One2many wht_line_ids where the vals omit company_id """
        # Simulating API payload lacking company_id in the inner One2many commands
        move = self.env['account.move'].with_company(self.company_a).create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company_a.id,
            'invoice_date': '2026-06-01',
            'invoice_line_ids': [
                Command.create({
                    'name': 'Product Line',
                    'quantity': 1,
                    'price_unit': 1000.0,
                    'account_id': self.account_expense.id,
                })
            ],
            'wht_line_ids': [
                Command.create({
                    'name': 'API WHT Line Test',
                    'account_id': self.account_wht.id,
                    'amount': 30.0,
                    # No company_id explicitly provided
                })
            ]
        })
        
        self.assertTrue(move.wht_line_ids, "WHT line should be created")
        for line in move.wht_line_ids:
            self.assertEqual(line.company_id.id, self.company_a.id, "company_id in batch create should fall back safely")
