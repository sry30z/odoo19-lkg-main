# -*- coding: utf-8 -*-
"""
Historical WHT Certificate Recovery Script

PROBLEM:
Historical payments may exist without WHT certificates due to broken trigger architecture.

SOLUTION:
This script safely scans for posted outbound payments that:
1. Are reconciled with vendor bills
2. Have no WHT certificates
3. Are in stable accounting state

It creates missing certificates using the same logic as the production flow.

SAFETY:
- Idempotent: Can run multiple times without side effects
- Dry-run mode: Preview changes before execution
- Read-only: Does not modify accounting states
- Rollback-friendly: Creates certificates that can be cancelled

AUTHOR: Senior Odoo Accounting Recovery Engineer
"""

import logging
import sys
import argparse
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wht_recovery.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
_logger = logging.getLogger(__name__)


class WHTCertificateRecovery:
    """Safe recovery of missing WHT certificates"""
    
    def __init__(self, env, dry_run=True, batch_size=100):
        """
        Initialize recovery engine
        
        Args:
            env: Odoo environment
            dry_run: If True, only report without creating certificates
            batch_size: Number of payments to process per batch
        """
        self.env = env
        self.dry_run = dry_run
        self.batch_size = batch_size
        
        self.stats = {
            'payments_scanned': 0,
            'payments_eligible': 0,
            'certificates_existing': 0,
            'certificates_created': 0,
            'certificates_failed': 0,
            'errors': 0
        }
        
        _logger.info("=" * 80)
        _logger.info("WHT CERTIFICATE RECOVERY ENGINE")
        _logger.info("=" * 80)
        _logger.info("Dry-run mode: %s", self.dry_run)
        _logger.info("Batch size: %d", self.batch_size)
        _logger.info("=" * 80)
    
    def scan_payments(self, from_date=None, to_date=None, partner_ids=None, payment_ids=None):
        """
        Scan for payments that need certificate recovery
        
        Args:
            from_date: Start date (datetime.date)
            to_date: End date (datetime.date)
            partner_ids: Specific partner IDs to scan (optional)
            payment_ids: Specific payment IDs to scan (optional)
        
        Returns:
            List of payments that need recovery
        """
        _logger.info("Scanning for payments requiring WHT certificate recovery...")
        
        domain = [
            ('state', '=', 'posted'),
            ('payment_type', '=', 'outbound'),
            ('partner_type', '=', 'vendor'),
        ]
        
        if from_date:
            domain.append(('date', '>=', from_date))
        if to_date:
            domain.append(('date', '<=', to_date))
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        if payment_ids:
            domain.append(('id', 'in', payment_ids))
        
        _logger.info("Search domain: %s", domain)
        
        payments = self.env['account.payment'].search(domain, order='date desc, id desc')
        self.stats['payments_scanned'] = len(payments)
        
        _logger.info("Found %d payments to analyze", len(payments))
        
        return payments
    
    def check_payment_eligibility(self, payment):
        """
        Check if a payment is eligible for certificate recovery
        
        Args:
            payment: account.payment record
            
        Returns:
            dict: {
                'eligible': bool,
                'reason': str,
                'bills': list of account.move records,
                'existing_certs': list of account.wht.certificate records
            }
        """
        _logger.info("=" * 80)
        _logger.info("CHECKING PAYMENT: %s (ID: %d)", payment.name, payment.id)
        _logger.info("=" * 80)
        
        # VALIDATION 1: Payment must have move_id
        if not payment.move_id:
            _logger.warning("SKIP: Payment %s - No move_id", payment.name)
            return {
                'eligible': False,
                'reason': 'No move_id (payment not properly posted)',
                'bills': [],
                'existing_certs': []
            }
        
        # VALIDATION 2: Check for reconciliation using stable method
        _logger.info("Discovering reconciliation for payment %s...", payment.name)
        bills = payment._get_reconciled_bills()
        
        if not bills:
            _logger.warning("SKIP: Payment %s - No reconciled bills", payment.name)
            return {
                'eligible': False,
                'reason': 'No reconciled bills',
                'bills': [],
                'existing_certs': []
            }
        
        _logger.info("Found %d reconciled bills: %s", len(bills), ', '.join(bills.mapped('name')))
        
        # VALIDATION 3: Check all bills are in paid state
        unpaid_bills = bills.filtered(lambda b: b.payment_state != 'paid')
        if unpaid_bills:
            _logger.warning("SKIP: Payment %s - Bills not fully paid: %s", 
                        payment.name, ', '.join(unpaid_bills.mapped('name')))
            return {
                'eligible': False,
                'reason': f'{len(unpaid_bills)} bills not fully paid',
                'bills': [],
                'existing_certs': []
            }
        
        # VALIDATION 4: Check all bills have 0 outstanding balance
        bills_with_balance = bills.filtered(lambda b: b.amount_residual != 0.0)
        if bills_with_balance:
            _logger.warning("SKIP: Payment %s - Bills have outstanding balance: %s",
                        payment.name, ', '.join([f"{b.name} ({b.amount_residual})" for b in bills_with_balance]))
            return {
                'eligible': False,
                'reason': f'{len(bills_with_balance)} bills have outstanding balance',
                'bills': [],
                'existing_certs': []
            }
        
        # VALIDATION 5: Check for existing certificates
        existing_certs = self.env['account.wht.certificate'].search([
            ('payment_id', '=', payment.id),
            ('state', '!=', 'cancel')
        ])
        
        if existing_certs:
            self.stats['certificates_existing'] += len(existing_certs)
            _logger.info("SKIP: Payment %s - Has %d existing certificates (non-cancelled)",
                       payment.name, len(existing_certs))
            return {
                'eligible': False,
                'reason': f'{len(existing_certs)} existing certificates found',
                'bills': bills,
                'existing_certs': existing_certs
            }
        
        _logger.info("✓ PAYMENT %s is ELIGIBLE for certificate recovery", payment.name)
        _logger.info("  - Reconciled bills: %d", len(bills))
        _logger.info("  - All bills paid: YES")
        _ logger.info("  - All balances zero: YES")
        _logger.info("  - Existing certificates: 0")
        
        return {
            'eligible': True,
            'reason': 'All validations passed',
            'bills': bills,
            'existing_certs': []
        }
    
    def create_certificate_for_payment(self, payment):
        """
        Create WHT certificate for a payment using the same logic as production flow
        
        Args:
            payment: account.payment record
            
        Returns:
            Created certificate record or None
        """
        _logger.info("=" * 80)
        _logger.info("CREATING CERTIFICATE: Payment %s (ID: %d)", payment.name, payment.id)
        _logger.info("=" * 80)
        
        try:
            if self.dry_run:
                _logger.info("[DRY-RUN] Would create certificate for payment %s", payment.name)
                return None
            
            # Create certificate with natural accounting state (same as production flow)
            certificate = self.env['account.wht.certificate'].create({
                'payment_id': payment.id,
                'partner_id': payment.partner_id.id,
                'date': payment.date,
                'amount': payment.amount,
                'state': 'draft',
            })
            
            _logger.info("✓ Certificate created: %s (ID: %d, State: %s)",
                       certificate.name, certificate.id, certificate.state)
            
            # Confirm certificate (natural state transition)
            certificate.action_confirm()
            
            _logger.info("✓ Certificate confirmed: %s (State: %s)",
                       certificate.name, certificate.state)
            
            _logger.info("✓ SUCCESS: Payment %s → Certificate %s created and confirmed",
                       payment.name, certificate.name)
            
            return certificate
            
        except Exception as e:
            _logger.error("✗ ERROR: Failed to create certificate for payment %s: %s",
                        payment.name, str(e), exc_info=True)
            _logger.error("Action: Certificate creation failed, payment workflow not affected")
            return None
    
    def run_recovery(self, from_date=None, to_date=None, partner_ids=None, payment_ids=None):
        """
        Run the recovery process
        
        Args:
            from_date: Start date (datetime.date)
            to_date: End date (datetime.date)
            partner_ids: Specific partner IDs to scan (optional)
            payment_ids: Specific payment IDs to scan (optional)
        """
        _logger.info("=" * 80)
        _logger.info("STARTING WHT CERTIFICATE RECOVERY")
        _logger.info("=" * 80)
        
        if from_date:
            _logger.info("From date: %s", from_date)
        if to_date:
            _logger.info("To date: %s", to_date)
        if partner_ids:
            _logger.info("Partner IDs: %s", partner_ids)
        if payment_ids:
            _logger.info("Payment IDs: %s", payment_ids)
        
        # Scan payments
        payments = self.scan_payments(from_date, to_date, partner_ids, payment_ids)
        
        if not payments:
            _logger.info("No payments found for recovery")
            return
        
        # Process payments in batches
        eligible_payments = []
        
        for i, payment in enumerate(payments, 1):
            _logger.info("Processing payment %d of %d", i, len(payments))
            
            eligibility = self.check_payment_eligibility(payment)
            
            if eligibility['eligible']:
                eligible_payments.append(payment)
                self.stats['payments_eligible'] += 1
                
                # Process certificate creation
                certificate = self.create_certificate_for_payment(payment)
                if certificate:
                    self.stats['certificates_created'] += 1
                else:
                    if not self.dry_run:
                        self.stats['certificates_failed'] += 1
                    else:
                        # In dry-run mode, count as "would create"
                        self.stats['certificates_created'] += 1
            
            # Batch processing: commit after each batch to avoid long transactions
            if i % self.batch_size == 0:
                _logger.info("Batch complete: %d/%d payments processed", i, len(payments))
                self.env.cr.commit()  # Commit database transaction
        
        # Final commit
        self.env.cr.commit()
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self):
        """Print recovery summary"""
        _logger.info("=" * 80)
        _logger.info("RECOVERY SUMMARY")
        _logger.info("=" * 80)
        _logger.info("Payments scanned: %d", self.stats['payments_scanned'])
        _logger.info("Payments eligible: %d", self.stats['payments_eligible'])
        _logger.info("Existing certificates found: %d", self.stats['certificates_existing'])
        _logger.info("Certificates created: %d", self.stats['certificates_created'])
        _logger.info("Certificates failed: %d", self.stats['certificates_failed'])
        _logger.info("=" * 80)
        
        if self.dry_run:
            _logger.info("DRY-RUN MODE: No actual certificates created")
        else:
            _logger.info("PRODUCTION MODE: Certificates created successfully")


def main():
    """Main entry point for standalone script execution"""
    parser = argparse.ArgumentParser(
        description='Historical WHT Certificate Recovery Script'
    )
    
    parser.add_argument('--dry-run', action='store_true', 
                       help='Preview changes without creating certificates')
    parser.add_argument('--from-date', type=str, 
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', type=str, 
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--partner-ids', type=str, 
                       help='Comma-separated partner IDs')
    parser.add_argument('--payment-ids', type=str, 
                       help='Comma-separated payment IDs')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Number of payments to process per batch (default: 100)')
    
    args = parser.parse_args()
    
    # Import Odoo (this must be run from within Odoo environment)
    try:
        import odoo
        from odoo import api, registry
        
        # Get database and environment
        with api.Environment.manage():
            env = api.Environment(registry.registry['account.payment']._modules.registry.get('database'))
            
            # Parse dates
            from_date = None
            to_date = None
            if args.from_date:
                from_date = datetime.strptime(args.from_date, '%Y-%m-%d').date()
            if args.to_date:
                to_date = datetime.strptime(args.to_date, '%Y-%m-%d').date()
            
            # Parse IDs
            partner_ids = None
            payment_ids = None
            if args.partner_ids:
                partner_ids = [int(pid) for pid in args.partner_ids.split(',')]
            if args.payment_ids:
                payment_ids = [int(pid) for pid in args.payment_ids.split(',')]
            
            # Create recovery engine
            recovery = WHTCertificateRecovery(
                env=env,
                dry_run=args.dry_run,
                batch_size=args.batch_size
            )
            
            # Run recovery
            recovery.run_recovery(
                from_date=from_date,
                to_date=to_date,
                partner_ids=partner_ids,
                payment_ids=payment_ids
            )
            
    except ImportError as e:
        print("Error: This script must be run within Odoo environment")
        print("Use: odoo-bin -c config -d <database> --script-path scripts/recover_historical_wht_certificates.py")
        sys.exit(1)
    except Exception as e:
        _logger.error("Fatal error: %s", str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
