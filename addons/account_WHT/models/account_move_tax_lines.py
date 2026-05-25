from odoo import fields, models, api



class AccountMoveTaxLines(models.Model):
    _name = 'account.move.tax.lines'
    _description = 'Account Move Tax Lines'
    _rec_name = 'name'
    
    _sql_constraints = [
        ('move_wht_tax_unique', 'UNIQUE(move_id, wht_tax_id)', 'Tax line already exists for this move and WHT tax')
    ]

    name = fields.Char()
    tax_id = fields.Many2one('account.tax')
    wht_tax_id = fields.Many2one('account.wht')
    account_id = fields.Many2one('account.account')
    amount = fields.Float()
    
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True,
        compute='_compute_company_id',
        store=True,
        readonly=True,
        help='Company for multi-company isolation'
    )

    move_id = fields.Many2one('account.move')
    
    @api.depends('move_id')
    def _compute_company_id(self):
        for rec in self:
            if rec.move_id and rec.move_id.company_id:
                rec.company_id = rec.move_id.company_id.id
