# -*- coding: utf-8 -*-
"""
Res Config Settings - Payment-Centric WHT Certificate UI

Provides UI configuration for WHT certificate grouping and auto-confirm settings.

Author: Payment-Centric WHT Refactoring
Date: 2026-05-22
"""

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    wht_certificate_grouping_strategy = fields.Selection(
        related='company_id.wht_certificate_grouping_strategy',
        string="WHT Certificate Grouping Strategy",
        help="How to group payments into WHT certificates for SME operations."
    )
    
    wht_auto_confirm_certificates = fields.Boolean(
        related='company_id.wht_auto_confirm_certificates',
        string="Auto-Confirm WHT Certificates",
        help="Automatically confirm WHT certificates when created from payments."
    )
