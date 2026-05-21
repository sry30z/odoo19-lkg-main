from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    signature_image = fields.Binary("Authorized Signature")
    signature_name = fields.Char("Signer Name")
    signature_position = fields.Char("Signer Position")
    wht_signer_mode = fields.Selection([
        ('signature', 'Signature'),
        ('name', 'Signer Name'),
    ], default='signature', string="WHT Signer Mode")

    # ===== Dynamic Report Theme (PDF-safe via QWeb) =====
    report_primary_color = fields.Char(
        string="Primary Report Color",
        default="#FDB813",
        help="Used to theme report headers/totals (PDF safe via wkhtmltopdf).",
    )
    report_secondary_color = fields.Char(
        string="Secondary Report Color",
        default="#f2f2f2",
        help="Used to theme report info boxes (PDF safe via wkhtmltopdf).",
    )
    report_alt_row_color = fields.Char(
        string="Alternate Row Color",
        default="#FFF9E6",
        help="Used to theme alternate table row background (PDF safe via wkhtmltopdf).",
    )
    report_text_color = fields.Char(
        string="Report Text Color",
        default="#333333",
        help="Used for report title/text color (PDF safe via wkhtmltopdf).",
    )
    report_border_color = fields.Char(
        string="Border Color",
        default="#000000",
        help="Used for report borders/lines (PDF safe via wkhtmltopdf).",
    )

    @api.model
    def _get_default_report_theme_values(self):
        return {
            'report_primary_color': '#FDB813',
            'report_secondary_color': '#f2f2f2',
            'report_alt_row_color': '#FFF9E6',
            'report_text_color': '#333333',
            'report_border_color': '#000000',
        }

    def action_reset_report_theme(self):
        """Reset theme colors to module defaults (company-safe)."""
        defaults = self._get_default_report_theme_values()
        self.write(defaults)

