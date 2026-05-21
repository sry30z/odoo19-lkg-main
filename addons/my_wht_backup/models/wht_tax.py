from odoo import models, fields

class WHTTax(models.Model):
    _name = 'wht.tax'
    _description = 'Withholding Tax'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    rate = fields.Float(string='Rate (%)', required=True)
    type = fields.Selection([
        ('service', 'Service'),
        ('rent', 'Rent'),
        ('professional', 'Professional')
    ], string='Type', required=True)
    income_type = fields.Char(string='Income Type', required=True)
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('vendor', 'Vendor'),
        ('both', 'Both')
    ], string='Partner Type', required=True)
    account_id = fields.Many2one('account.account', string='Account', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)