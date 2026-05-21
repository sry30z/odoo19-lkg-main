from odoo import fields, models



class AccountMoveTaxLines(models.Model):
    _name = 'account.move.tax.lines'
    _description = 'Account Move Tax Lines'
    _rec_name = 'name'

    name = fields.Char()
    tax_id = fields.Many2one('account.tax')
    wht_tax_id = fields.Many2one('account.wht')
    account_id = fields.Many2one('account.account')
    amount = fields.Float()

    move_id = fields.Many2one('account.move')
