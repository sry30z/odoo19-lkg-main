import logging
from odoo import fields
_logger = logging.getLogger('test_wht')
_logger.warning('========== START REAL TEST FLOW ==========')

partner = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
if not partner:
    partner = env['res.partner'].create({'name': 'Test Vendor', 'supplier_rank': 1})

# Create bill
move = env['account.move'].create({
    'move_type': 'in_invoice',
    'partner_id': partner.id,
    'invoice_date': fields.Date.today(),
    'invoice_line_ids': [(0, 0, {
        'name': 'Test Service',
        'quantity': 1.0,
        'price_unit': 1000.0,
    })]
})
move.action_post()
_logger.warning("Bill posted: %s", move.name)

# Make sure WHT tax exists
wht_tax = env['account.wht'].search([('tax_application', '=', 'payment')], limit=1)
if not wht_tax:
    _logger.warning("NO WHT TAX FOUND")

# Open wizard
ctx = {'active_model': 'account.move', 'active_ids': [move.id]}
wizard = env['account.payment.register'].with_context(**ctx).create({
    'payment_date': fields.Date.today(),
})

# Wait, calling default_get first to simulate real flow
defaults = env['account.payment.register'].with_context(**ctx).default_get(['sub_amount', 'wht_line_ids', 'is_wht', 'wht_type', 'wht_pay_type', 'amount', 'currency_id'])
wizard = env['account.payment.register'].with_context(**ctx).create(defaults)

if not wizard.wht_line_ids and wht_tax:
    wizard.wht_line_ids = [(0, 0, {
        'wht_id': wht_tax.id,
        'base_amount': 1000.0,
        'amount': 30.0,
    })]
    wizard.is_wht = True

_logger.warning("Wizard ready. is_wht=%s, lines=%s", wizard.is_wht, wizard.wht_line_ids.ids)

# Run create payment
payments = wizard.action_create_payments()
_logger.warning("Payments created: %s", payments)

env.cr.commit()
_logger.warning('========== END REAL TEST FLOW ==========')
