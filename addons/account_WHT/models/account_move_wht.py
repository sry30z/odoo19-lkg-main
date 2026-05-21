# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveWHT(models.Model):
    _name = 'account.move.wht'
    _description = "Account Move WHT"
    _rec_name = 'name'

    name = fields.Char('Name')
    account_id = fields.Many2one('account.account', 'WHT Account')
    amount = fields.Monetary('Amount Deducted')

    move_id = fields.Many2one(
        'account.move',
        'Invoice',
        ondelete='cascade')

    currency_id = fields.Many2one(
        'res.currency',
        related='move_id.currency_id',
        store=True,
        readonly=True)