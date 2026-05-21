from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    wht_id = fields.Many2one('wht.tax', string='Withholding Tax')
    wht_amount = fields.Monetary(string='WHT Amount', compute='_compute_wht_amount', store=True)

    @api.depends('wht_id', 'amount_total')
    def _compute_wht_amount(self):
        for record in self:
            if record.wht_id:
                record.wht_amount = (record.amount_total * record.wht_id.rate) / 100
            else:
                record.wht_amount = 0