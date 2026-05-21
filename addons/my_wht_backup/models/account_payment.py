from odoo import models, fields, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    wht_id = fields.Many2one('wht.tax', string='Withholding Tax')
    wht_amount = fields.Monetary(string='WHT Amount', compute='_compute_wht_amount', store=True)

    @api.depends('wht_id', 'amount')
    def _compute_wht_amount(self):
        for record in self:
            if record.wht_id:
                record.wht_amount = (record.amount * record.wht_id.rate) / 100
            else:
                record.wht_amount = 0