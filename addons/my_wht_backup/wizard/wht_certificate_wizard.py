from odoo import models, fields, api

class WHTCertificateWizard(models.TransientModel):
    _name = 'wht.certificate.wizard'
    _description = 'WHT Certificate Wizard'

    payment_ids = fields.Many2many('account.payment', string='Payments')

    def generate_certificates(self):
        return self.env.ref('my_wht.action_report_wht_certificate').report_action(self.payment_ids)