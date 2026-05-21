# -*- coding: utf-8 -*-
import base64
from odoo import models, fields, api

class WhtExportWizard(models.TransientModel):
    _name = 'wht.export.wizard'
    _description = 'WHT Export Wizard for PND 3 / 53'

    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    wht_type = fields.Selection([
        ('pnd3', 'P.N.D. 3'),
        ('pnd53', 'P.N.D. 53'),
    ], string='WHT Type', required=True)
    export_file = fields.Binary('Export File', readonly=True)
    export_filename = fields.Char('File Name', readonly=True)
    state = fields.Selection([('choose', 'Choose'), ('get', 'Get')], default='choose')

    def action_export(self):
        domain = [
            ('issue_date', '>=', self.date_from), 
            ('issue_date', '<=', self.date_to),
            ('wht_type', '=', self.wht_type),
            ('state', '=', 'done')
        ]
        certs = self.env['account.wht.certificate'].search(domain)
        
        lines = []
        seq = 1
        for cert in certs:
            partner = cert.partner_id
            tax_id = cert.partner_taxid or ''
            name = partner.name or ''
            
            # Dynamic branch lookup
            branch = '00000'
            for field in ['vat_branch', 'branch_code', 'branch_no', 'branch']:
                if hasattr(partner, field) and getattr(partner, field):
                    branch_val = str(getattr(partner, field))
                    if branch_val.isdigit():
                        branch = branch_val.zfill(5)
                        break
            
            address = (cert.partner_address or '').replace('\n', ' ').replace('\r', ' ')
            issue_date_str = cert.issue_date.strftime('%d/%m/%Y') if cert.issue_date else ''
            
            for cert_line in cert.line_ids:
                rate = 0.0
                if cert_line.base_amount:
                    rate = round((cert_line.tax_amount / cert_line.base_amount) * 100, 2)
                rate_str = f"{rate:.2f}" if rate % 1 else f"{int(rate)}"
                
                income_desc = cert_line.income_type_name or cert_line.income_type_text or 'บริการ'
                
                condition = '1'
                if cert_line.wht_pay_type == 'gross_up_forever':
                    condition = '2'
                elif cert_line.wht_pay_type == 'gross_up_once':
                    condition = '3'
                
                line = [
                    str(seq),
                    tax_id,
                    '', # Title
                    name,
                    branch,
                    address,
                    issue_date_str,
                    income_desc,
                    rate_str,
                    f"{cert_line.base_amount:.2f}",
                    f"{cert_line.tax_amount:.2f}",
                    condition
                ]
                lines.append("|".join(line))
                seq += 1
            
        file_content = "\r\n".join(lines)
        file_data = base64.b64encode(file_content.encode('tis-620', errors='ignore')) # Revenue department uses TIS-620
        
        self.write({
            'export_file': file_data,
            'export_filename': f'WHT_{self.wht_type}_{self.date_from.strftime("%Y%m")}.txt',
            'state': 'get'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wht.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
