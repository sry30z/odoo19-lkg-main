# -*- coding: utf-8 -*-
from odoo import fields, models, api


class AccountMoveWHT(models.Model):
    _name = 'account.move.wht'
    _description = "Account Move WHT"
    _rec_name = 'name'

    name = fields.Char('Name')
    account_id = fields.Many2one('account.account', 'WHT Account')
    amount = fields.Monetary('Amount Deducted')
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        compute='_compute_company_id',
        store=True,
        readonly=True,
        help='Company for multi-company isolation'
    )

    move_id = fields.Many2one(
        'account.move',
        'Invoice',
        ondelete='cascade')

    currency_id = fields.Many2one(
        'res.currency',
        related='move_id.currency_id',
        store=True,
        readonly=True)
    
    @api.depends('move_id')
    def _compute_company_id(self):
        for rec in self:
            if rec.move_id and rec.move_id.company_id:
                rec.company_id = rec.move_id.company_id.id