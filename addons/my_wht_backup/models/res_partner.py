from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    default_wht_id = fields.Many2one('wht.tax', string='Default WHT')
    tax_id = fields.Char(string='Tax ID')
    branch_no = fields.Char(string='Branch Number')
    partner_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company')
    ], string='Partner Type')