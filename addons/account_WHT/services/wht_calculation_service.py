# -*- coding: utf-8 -*-
"""
WHT Calculation Service Layer - Single Source of Truth for WHT Calculations

This service provides deterministic WHT calculations that always return
the same result for the same inputs, eliminating non-deterministic behavior
from the WHT flow.

Author: Deterministic WHT Refactoring
Date: 2026-05-22
"""

from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class WHTCalculationService(models.AbstractModel):
    """
    WHT Calculation Service - Central Engine for WHT Calculations
    
    This service provides pure functions for WHT calculations that are:
    - Deterministic: Same input always produces same output
    - Idempotent: Can be called multiple times safely
    - Stateless: No side effects
    - Testable: Easy to unit test
    """
    
    _name = 'wht.calculation.service'
    _description = 'WHT Calculation Service'
    
    @api.model
    def calculate_wht(self, base_amount, rate, wht_pay_type, rounding=2):
        """
        Pure WHT calculation - always returns same result for same inputs
        
        This is the SINGLE SOURCE OF TRUTH for all WHT calculations.
        All other parts of the system should use this method.
        
        Args:
            base_amount (float): Base amount before WHT
            rate (float): WHT rate in percentage (e.g., 3.0 for 3%)
            wht_pay_type (str): Payment type
                - 'normal': Normal withholding (หัก ณ ที่จ่าย)
                - 'gross_up_forever': Gross up forever (ออกให้ตลอด)
                - 'gross_up_once': Gross up once (ออกให้ครั้งเดียว)
            rounding (int): Number of decimal places for rounding (default: 2)
        
        Returns:
            dict: Dictionary with keys:
                - base (float): Base amount after gross-up calculation
                - wht (float): WHT amount
                - gross_up (float): Gross-up amount (0 if normal)
        
        Raises:
            ValueError: If rate is 100% for gross-up_forever (division by zero)
            UserError: If invalid parameters
        
        Examples:
            >>> service.calculate_wht(1000, 3, 'normal')
            {'base': 1000.0, 'wht': 30.0, 'gross_up': 0.0}
            
            >>> service.calculate_wht(1000, 3, 'gross_up_forever')
            {'base': 1030.93, 'wht': 30.93, 'gross_up': 30.93}
        """
        # Validate inputs
        if base_amount < 0:
            raise UserError(_("Base amount cannot be negative"))
        if rate < 0:
            raise UserError(_("WHT rate cannot be negative"))
        if wht_pay_type not in ['normal', 'gross_up_forever', 'gross_up_once']:
            raise UserError(_("Invalid WHT pay type: %s") % wht_pay_type)
        
        rate_decimal = rate / 100.0
        
        if wht_pay_type == 'gross_up_forever':
            # Gross up forever: base includes WHT
            if abs(1 - rate_decimal) < 1e-9:
                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation"))
            
            base = round(base_amount / (1 - rate_decimal), rounding)
            wht = round(base * rate_decimal, rounding)
            gross_up = wht
            net = base_amount
            total = base
            
        elif wht_pay_type == 'gross_up_once':
            # Gross up once: tax is calculated on the original amount
            wht = round(base_amount * rate_decimal, rounding)
            base = base_amount
            gross_up = wht
            net = base_amount
            total = base_amount + wht
            
        else:
            # Normal withholding: WHT deducted from payment
            base = base_amount
            wht = round(base * rate_decimal, rounding)
            gross_up = 0.0
            net = round(base_amount - wht, rounding)
            total = base_amount
        
        return {
            'base': base,
            'wht': wht,
            'gross_up': gross_up,
            'net': net,
            'total': total
        }
    
    @api.model
    def calculate_tax_on_tax_wht(self, tax_amount, rate, wht_pay_type, rounding=2):
        """
        Calculate WHT on tax amount (Tax on Tax)
        
        Args:
            tax_amount (float): Tax amount before WHT
            rate (float): WHT rate in percentage
            wht_pay_type (str): Payment type
            rounding (int): Decimal places for rounding
        
        Returns:
            dict: Same format as calculate_wht
        """
        return self.calculate_wht(tax_amount, rate, wht_pay_type, rounding)
    
    @api.model
    def calculate_invoice_wht(self, invoice):
        """
        Calculate WHT for entire invoice
        
        This method aggregates WHT calculations across all invoice lines
        and provides both line-level and totals.
        
        Args:
            invoice (account.move): Invoice record
        
        Returns:
            dict: Dictionary with keys:
                - by_line (list): List of WHT calculations per line
                - total (dict): Totals across all lines
                    - base (float): Total base amount
                    - wht (float): Total WHT amount
                    - gross_up (float): Total gross-up amount
        """
        result = {
            'by_line': [],
            'total': {'base': 0.0, 'wht': 0.0, 'gross_up': 0.0, 'net': 0.0, 'total': 0.0}
        }
        
        for line in invoice.invoice_line_ids:
            for wht_tax in line.wht_tax_ids:
                try:
                    # Use the single source of truth calculation
                    calc = self.calculate_wht(
                        line.price_subtotal,
                        wht_tax.amount,
                        invoice.wht_pay_type
                    )
                    
                    result['by_line'].append({
                        'line_id': line.id,
                        'line_name': line.name,
                        'wht_tax_id': wht_tax.id,
                        'wht_tax_name': wht_tax.name,
                        **calc
                    })
                    
                    # Accumulate totals
                    result['total']['base'] += calc['base']
                    result['total']['wht'] += calc['wht']
                    result['total']['gross_up'] += calc['gross_up']
                    result['total']['net'] += calc['net']
                    result['total']['total'] += calc['total']
                    
                except (UserError, ValueError) as e:
                    _logger.warning(
                        "WHT calculation failed for line %s, tax %s: %s",
                        line.id, wht_tax.id, str(e)
                    )
                    # Skip this line/tax combination
                    continue
        
        # Round totals to avoid floating point accumulation errors
        result['total']['base'] = round(result['total']['base'], 2)
        result['total']['wht'] = round(result['total']['wht'], 2)
        result['total']['gross_up'] = round(result['total']['gross_up'], 2)
        result['total']['net'] = round(result['total']['net'], 2)
        result['total']['total'] = round(result['total']['total'], 2)
        
        return result
    
    @api.model
    def calculate_payment_ratio(self, payment, invoices):
        """
        Calculate payment ratio for partial payments
        
        Args:
            payment (account.payment): Payment record
            invoices (account.move): Invoice records being paid
        
        Returns:
            float: Payment ratio (0.0 to 1.0)
        """
        if not invoices:
            return 0.0
        
        # Calculate total invoice net (base) amount
        service = self
        total_invoice_base = 0.0
        
        for invoice in invoices:
            invoice_wht = service.calculate_invoice_wht(invoice)
            total_invoice_base += invoice_wht['total']['base']
        
        if not total_invoice_base:
            return 0.0
        
        # Calculate ratio
        ratio = payment.amount / total_invoice_base
        return min(1.0, max(0.0, ratio))
    
    @api.model
    def calculate_payment_wht(self, payment, invoices):
        """
        Calculate WHT for payment based on payment ratio
        
        This provides deterministic WHT calculation for payments, accounting
        for partial payments and payment ratio distribution.
        
        Args:
            payment (account.payment): Payment record
            invoices (account.move): Invoice records being reconciled
        
        Returns:
            dict: Dictionary with keys:
                - total_wht (float): Total WHT amount for this payment
                - total_base (float): Total base amount for this payment
                - ratio (float): Payment ratio used
                - by_invoice (list): WHT breakdown per invoice
        """
        if not invoices:
            return {
                'total_wht': 0.0,
                'total_base': 0.0,
                'ratio': 0.0,
                'by_invoice': []
            }
        
        # Calculate payment ratio
        ratio = self.calculate_payment_ratio(payment, invoices)
        
        result = {
            'total_wht': 0.0,
            'total_base': 0.0,
            'ratio': ratio,
            'by_invoice': []
        }
        
        for invoice in invoices:
            # Calculate full invoice WHT
            invoice_wht = self.calculate_invoice_wht(invoice)
            
            # Calculate this payment's share
            payment_wht = round(invoice_wht['total']['wht'] * ratio, 2)
            payment_base = round(invoice_wht['total']['base'] * ratio, 2)
            
            invoice_payment_wht = {
                'invoice_id': invoice.id,
                'invoice_name': invoice.name,
                'ratio': ratio,
                'full_wht': invoice_wht['total']['wht'],
                'payment_wht': payment_wht,
                'full_base': invoice_wht['total']['base'],
                'payment_base': payment_base,
                'wht_pay_type': invoice.wht_pay_type,
            }
            
            # Store line-level breakdown
            invoice_payment_wht['by_line'] = []
            for line_wht in invoice_wht['by_line']:
                line_payment_wht = line_wht.copy()
                line_payment_wht['base'] = round(line_wht['base'] * ratio, 2)
                line_payment_wht['wht'] = round(line_wht['wht'] * ratio, 2)
                line_payment_wht['gross_up'] = round(line_wht['gross_up'] * ratio, 2)
                invoice_payment_wht['by_line'].append(line_payment_wht)
            
            result['by_invoice'].append(invoice_payment_wht)
            result['total_wht'] += payment_wht
            result['total_base'] += payment_base
        
        # Round totals
        result['total_wht'] = round(result['total_wht'], 2)
        result['total_base'] = round(result['total_base'], 2)
        
        return result
    
    @api.model
    def validate_wht_calculation_consistency(self, invoice):
        """
        Validate WHT calculation consistency across different sources
        
        This method checks if the calculated WHT matches stored values
        in the invoice's computed fields and tax lines.
        
        Args:
            invoice (account.move): Invoice record
        
        Returns:
            dict: Validation result with keys:
                - is_consistent (bool): Whether calculations match
                - differences (list): List of differences found
                - calculated (dict): Calculated values
                - stored (dict): Stored values
        """
        calculated = self.calculate_invoice_wht(invoice)
        
        stored = {
            'wht_base_amount': invoice.wht_base_amount if hasattr(invoice, 'wht_base_amount') else 0.0,
            'wht_amount': invoice.wht_amount if hasattr(invoice, 'wht_amount') else 0.0,
        }
        
        differences = []
        is_consistent = True
        
        # Check base amount
        if abs(calculated['total']['base'] - stored['wht_base_amount']) > 0.01:
            differences.append({
                'field': 'wht_base_amount',
                'calculated': calculated['total']['base'],
                'stored': stored['wht_base_amount'],
                'diff': abs(calculated['total']['base'] - stored['wht_base_amount'])
            })
            is_consistent = False
        
        # Check WHT amount
        if abs(calculated['total']['wht'] - stored['wht_amount']) > 0.01:
            differences.append({
                'field': 'wht_amount',
                'calculated': calculated['total']['wht'],
                'stored': stored['wht_amount'],
                'diff': abs(calculated['total']['wht'] - stored['wht_amount'])
            })
            is_consistent = False
        
        return {
            'is_consistent': is_consistent,
            'differences': differences,
            'calculated': calculated,
            'stored': stored
        }
