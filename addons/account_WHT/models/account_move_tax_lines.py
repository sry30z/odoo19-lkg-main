# -*- coding: utf-8 -*-
# HOTFIX: account_move_tax_lines.py
# ────────────────────────────────────────────────────────────────────────────
# ROOT CAUSE FIX:
#   company_id เดิมถูกกำหนดเป็น compute='_compute_company_id' + required=True
#   ซึ่งทำให้เกิด ValidationError ใน production เพราะ Odoo 18 validate required
#   fields ก่อนที่ compute จะทำงาน (race condition)
#
# SOLUTION:
#   เปลี่ยนเป็น default=lambda self: self.env.company ซึ่ง:
#     1. รับประกัน company_id มีค่าก่อน ORM create
#     2. ทุก creation path ที่ส่ง company_id ผ่าน vals จะ override ค่า default นี้
#     3. Backward compatible กับ records เดิม (store=True เดิม)
# ────────────────────────────────────────────────────────────────────────────
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)

class AccountMoveTaxLines(models.Model):
    _name = 'account.move.tax.lines'
    _description = 'Account Move Tax Lines'
    _rec_name = 'name'

    _sql_constraints = [
        ('move_wht_tax_unique', 'UNIQUE(move_id, wht_tax_id)',
         'Tax line already exists for this move and WHT tax')
    ]

    name = fields.Char()
    tax_id = fields.Many2one('account.tax')
    wht_tax_id = fields.Many2one('account.wht')
    account_id = fields.Many2one('account.account')
    amount = fields.Float()

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
             'Set explicitly on creation to ensure correct company in multi-company setups.'
    )

    move_id = fields.Many2one('account.move')

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
                
                _logger.warning("account_WHT: company_id missing in create vals for account.move.tax.lines, auto-populated from move/company context")

        return super().create(vals_list)
