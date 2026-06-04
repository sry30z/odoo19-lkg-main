# -*- coding: utf-8 -*-
# HOTFIX: account_move_wht.py
# ────────────────────────────────────────────────────────────────────────────
# ROOT CAUSE FIX (เหมือน account_move_tax_lines.py):
#   company_id เดิมถูกกำหนดเป็น compute='_compute_company_id' + required=True
#   ซึ่งทำให้เกิด ValidationError เมื่อ create_wht_line() ถูกเรียกจาก action_post()
#   เพราะ Odoo 18 validate required fields ก่อน compute ทำงาน
#
# SOLUTION:
#   เปลี่ยนเป็น default=lambda self: self.env.company
#   create_wht_line() ใน account_move.py ถูกแก้ให้ส่ง company_id ใน vals โดยตรงแล้ว
# ────────────────────────────────────────────────────────────────────────────
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)

class AccountMoveWHT(models.Model):
    _name = 'account.move.wht'
    _description = "Account Move WHT"
    _rec_name = 'name'

    name = fields.Char('Name')
    account_id = fields.Many2one('account.account', 'WHT Account')
    amount = fields.Monetary('Amount Deducted')

    # PHASE 3: KEEP COMPUTE FOR COMPATIBILITY
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        compute='_compute_company_id',
        store=True,
        index=True,
        help='Company for multi-company isolation. '
             'Set explicitly on creation via create_wht_line() to ensure correctness.'
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
            elif not rec.company_id:
                rec.company_id = self.env.company.id

    @api.model_create_multi
    def create(self, vals_list):
        # PHASE 4: CREATE SAFETY NET & PHASE 7: INCIDENT PREVENTION
        for vals in vals_list:
            if not vals.get('company_id'):
                move = False
                if vals.get('move_id'):
                    move = self.env['account.move'].browse(vals['move_id'])
                
                vals['company_id'] = (
                    move.company_id.id
                    if move and move.exists() and move.company_id
                    else self.env.company.id
                )
                
                _logger.warning("account_WHT: company_id missing in create vals for account.move.wht, auto-populated from move/company context")

        return super().create(vals_list)