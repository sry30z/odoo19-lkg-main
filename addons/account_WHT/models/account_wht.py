from odoo import fields, models, api, tools, _
import base64
import os
from odoo.modules.module import get_module_resource

class WhtIncomeType(models.Model):
    _name = 'wht.income.type'
    _description = 'WHT Income Type Master Data'
    _order = 'sequence, code'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    certificate_line_ids = fields.One2many(
        'account.wht.certificate.line', 'income_type_id', 
        string='WHT Lines'
    )
    total_base = fields.Float(
        string='Total Base Amount', 
        compute='_compute_totals',
        help='Total Base Amount accumulated under this income type from confirmed WHT certificates.'
    )
    total_tax = fields.Float(
        string='Total Tax Amount', 
        compute='_compute_totals',
        help='Total Tax Amount accumulated under this income type from confirmed WHT certificates.'
    )

    @api.depends('certificate_line_ids.base_amount', 'certificate_line_ids.tax_amount', 'certificate_line_ids.certificate_id.state')
    def _compute_totals(self):
        for rec in self:
            lines = rec.certificate_line_ids.filtered(lambda line: line.certificate_id.state == 'done')
            rec.total_base = sum(lines.mapped('base_amount'))
            rec.total_tax = sum(lines.mapped('tax_amount'))
    
    # ประเภทแบบยื่นภาษีหัก ณ ที่จ่าย — ครบทุกประเภทตามมาตรฐานกรมสรรพากร
    pnd_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string='Default PND Type')
    
    display_name_full = fields.Char(
        string='Display Name', 
        compute='_compute_display_name_full', 
        store=True
    )

    @api.depends('code', 'name')
    def _compute_display_name_full(self):
        for rec in self:
            if rec.code and rec.name:
                rec.display_name_full = f"{rec.code}. {rec.name}"
            else:
                rec.display_name_full = rec.name or rec.code or 'New'

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, rec.display_name_full))
        return result


class AccountWHTCertificate(models.Model):
    _name = "account.wht.certificate"
    _description = "WHT Certificate"
    _rec_name = "certificate_no"

    certificate_no = fields.Char(
        string="Certificate No.",
        required=True,
        copy=False,
        readonly=True,
        default="New",
    )
    issue_date = fields.Date(string="Issue Date", default=fields.Date.context_today)

    # General Information fields
    wht_book_no = fields.Char(string="WHT Book No.")
    wht_kind = fields.Selection([
        ('send', 'Send'),
        ('receive', 'Receive'),
    ], string="Type", default='send')
    wht_type = fields.Selection([
        ('pnd1',         'ภ.ง.ด.1'),
        ('pnd1k',        'ภ.ง.ด.1ก'),
        ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
        ('pnd2',         'ภ.ง.ด.2'),
        ('pnd2k',        'ภ.ง.ด.2ก'),
        ('pnd3',         'ภ.ง.ด.3'),
        ('pnd3k',        'ภ.ง.ด.3ก'),
        ('pnd53',        'ภ.ง.ด.53'),
    ], string="WHT Type", default='pnd53')
    income_type = fields.Selection([
        ('service', 'Service'),
        ('rent', 'Rent'),
        ('other', 'Other'),
    ], string="Income Type", default='service')
    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal', tracking=True)
    sequence = fields.Integer(string="Sequence", default=0)

    # Payee Information
    partner_id = fields.Many2one("res.partner", string="Partner", required=True)
    partner_taxid = fields.Char(string="Partner Tax ID", copy=False)
    partner_address = fields.Text(string="Partner Address", copy=False)

    # Misc Information
    wht_reference = fields.Char(string="Reference", help="Source documents")
    user_pay_id = fields.Many2one('res.users', string="User Pay", default=lambda self: self.env.user)
    display_user_signature = fields.Boolean(string="Display User Signature?", default=True)
    display_company_seal = fields.Boolean(string="Display Company Seal?", default=True)
    pay_date = fields.Date(string="Pay Date", default=fields.Date.context_today)
    payment_id = fields.Many2one("account.payment", string="Payment")
    move_id = fields.Many2one("account.move", string="Bill/Invoice (Legacy)")
    move_ids = fields.Many2many("account.move", string="Bills/Invoices")
    bill_count = fields.Integer(string="Bill Count", compute="_compute_bill_count")

    # Payer Information
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    company_taxid = fields.Char(related="company_id.vat", string="Company Tax ID")
    company_address = fields.Char(string="Company Address", compute='_compute_company_address', store=True)

    # Detail Lines
    line_ids = fields.One2many('account.wht.certificate.line', 'certificate_id', string="WHT Detail Lines")

    base_amount = fields.Monetary(string="Base Amount", compute="_compute_amounts", store=True)
    tax_amount = fields.Monetary(string="WHT Amount", compute="_compute_amounts", store=True)

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for rec in self:
            if rec.partner_id:
                rec.partner_taxid = rec.partner_id.vat
                # Use _display_address(without_company=True) to exclude the partner name from the address string
                rec.partner_address = rec.partner_id._display_address(without_company=True)

    @api.depends('company_id')
    def _compute_company_address(self):
        for rec in self:
            if rec.company_id and rec.company_id.partner_id:
                # Use without_company=True to ensure the company name isn't duplicated in the address field
                rec.company_address = rec.company_id.partner_id._display_address(without_company=True)
            else:
                rec.company_address = ''

    @api.depends('line_ids.base_amount', 'line_ids.tax_amount')
    def _compute_amounts(self):
        for rec in self:
            rec.base_amount = sum(rec.line_ids.mapped('base_amount'))
            rec.tax_amount = sum(rec.line_ids.mapped('tax_amount'))

    @api.depends("move_ids")
    def _compute_bill_count(self):
        for rec in self:
            rec.bill_count = len(rec.move_ids)

    def action_view_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills/Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'context': {'create': False},
        }

    @api.model
    def default_get(self, fields_list):
        res = super(AccountWHTCertificate, self).default_get(fields_list)
        res.update({'income_type': 'service'})
        return res

    def action_confirm(self):
        for rec in self:
            if rec.certificate_no in ('New', 'Draft'):
                rec.certificate_no = self.env['ir.sequence'].next_by_code('account.wht.certificate') or rec.certificate_no
            rec.state = 'done'

    def action_recompute_from_bills(self):
        """ดึงรายการภาษีใหม่จากบิลที่เชื่อมโยง — ใช้ได้เฉพาะสถานะ Draft"""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.move_ids:
                continue

            new_lines = []
            for move in rec.move_ids:
                for inv_line in move.invoice_line_ids:
                    for wht in inv_line.wht_tax_ids:
                        rate = wht.amount / 100.0
                        l_base = inv_line.price_subtotal
                        
                        if move.wht_pay_type == 'gross_up_forever':
                            if abs(1 - rate) < 1e-9:
                                continue
                            l_base = l_base / (1 - rate)
                        elif move.wht_pay_type == 'gross_up_once':
                            l_base = l_base + (l_base * rate)
                            
                        l_tax = round(l_base * rate, 2)
                        new_lines.append((0, 0, {
                            'income_type_id': wht.income_type_id.id if wht.income_type_id else False,
                            'income_type_code': wht.income_type_id.code if wht.income_type_id else '',
                            'income_type_name': wht.income_type_id.name if wht.income_type_id else '',
                            'income_type_text': wht.description or wht.name or 'Service',
                            'name': wht.name,
                            'base_amount': l_base,
                            'tax_amount': l_tax,
                            'invoice_move_id': move.id,
                            'wht_pay_type': move.wht_pay_type,
                        }))

            # ลบรายการเดิมออกก่อนแล้วแทนใหม่
            rec.write({
                'line_ids': [(5, 0, 0)] + new_lines,
                'wht_reference': ', '.join(rec.move_ids.mapped('name')),
            })

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def action_print_50_bis(self):
        for rec in self:
            if rec.state != 'done':
                raise models.ValidationError(_("Cannot print 50 Bis unless the WHT Certificate is Done. / ไม่สามารถพิมพ์ 50 ทวิได้หากสถานะ WHT Certificate ยังไม่เสร็จสิ้น (Done)"))
        return self.env.ref("account_WHT.action_report_wht_50_bis").report_action(self)

    def action_print_50tawi(self):
        for rec in self:
            if rec.state != 'done':
                raise models.ValidationError(_("Cannot print 50 Tawi unless the WHT Certificate is Done. / ไม่สามารถพิมพ์ 50 ทวิได้หากสถานะ WHT Certificate ยังไม่เสร็จสิ้น (Done)"))
        return self.env.ref('account_WHT.action_wht_50tawi').report_action(self)

    def action_preview_50tawi(self):
        """Preview ในรูปแบบ HTML เพื่อช่วยในการตรวจสอบรูปแบบ (Format)"""
        self.ensure_one()
        action = self.env.ref('account_WHT.action_wht_50tawi').report_action(self)
        action['report_type'] = 'qweb-html'
        return action

    def action_send_email(self):
        self.ensure_one()
        if self.state == 'draft':
            raise models.ValidationError(_("Cannot send email for a draft WHT Certificate. Please confirm it first."))

        ctx = {
            'default_model': 'account.wht.certificate',
            'default_res_ids': self.ids,
            'default_use_template': False,
            'default_composition_mode': 'comment',
            'default_partner_ids': [(6, 0, [self.partner_id.id])] if self.partner_id else [],
            'default_subject': f'หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ) - {self.certificate_no}',
            'default_body': f'<p>เรียน {self.partner_id.name or "ท่านคู่ค้า"},</p><p>บริษัทได้จัดทำและส่งหนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ) เลขที่ <b>{self.certificate_no}</b> มาพร้อมกับอีเมลฉบับนี้</p><br/><p>ขอแสดงความนับถือ</p>',
        }

        report_action = self.env.ref('account_WHT.action_wht_50tawi', raise_if_not_found=False)
        if report_action:
            pdf_content = self.env['ir.actions.report']._render_qweb_pdf('account_WHT.action_wht_50tawi', [self.id])[0]
            attachment = self.env['ir.attachment'].create({
                'name': f'WHT_50Tawi_{self.certificate_no}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'account.wht.certificate',
                'res_id': self.id,
                'mimetype': 'application/pdf'
            })
            ctx['default_attachment_ids'] = [(6, 0, [attachment.id])]

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'target': 'new',
            'context': ctx,
        }

    def action_export_rd_txt(self):
        lines = []
        for rec in self:
            tax_id = rec.partner_taxid or ''
            name = rec.partner_id.name or ''
            amount = "{:.2f}".format(rec.base_amount or 0.0)
            tax = "{:.2f}".format(rec.tax_amount or 0.0)
            # Use pipe '|' delimiter as per user requirement (tax_id | name | amount | tax)
            line = f"{tax_id}|{name}|{amount}|{tax}"
            lines.append(line)
            
        # Convert to TIS-620 or UTF-8. Odoo default is UTF-8, but RD often requires TIS-620/Windows-874.
        # We'll use windows-874 to be safe with Thai RD systems if requested, otherwise utf-8.
        # But let's stick to utf-8 unless specified. RD modern systems accept UTF-8 but some legacy require TIS-620.
        # Since it's a simple export, let's use utf-8.
        txt_content = "\r\n".join(lines)
        
        attachment = self.env['ir.attachment'].create({
            'name': 'RD_Export.txt',
            'type': 'binary',
            'datas': base64.b64encode(txt_content.encode('utf-8')),
            'res_model': 'account.wht.certificate',
            'mimetype': 'text/plain'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def get_wht_background_base64(self):
        """Helper to get static background as base64 for wkhtmltopdf reliability"""
        addon_path = get_module_resource('account_WHT', 'static', 'src', 'img', '50tawi_bg.png')
        if addon_path and os.path.exists(addon_path):
            with open(addon_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('ascii')
                return f"data:image/png;base64,{img_data}"
        return ""

    def get_grouped_income_lines(self):
        """Helper for 50 Tawi Report to group line amounts by income type code."""
        self.ensure_one()
        groups = {}
        for line in self.line_ids:
            code = line.income_type_code or '6'
            if code not in groups:
                groups[code] = {
                    'code': code,
                    'name': line.name,
                    'date': line.pay_date or self.issue_date,
                    'base_amount': 0.0,
                    'tax_amount': 0.0,
                }
            groups[code]['base_amount'] += line.base_amount
            groups[code]['tax_amount'] += line.tax_amount
        return groups.values()


class AccountWHTCertificateLine(models.Model):
    _name = "account.wht.certificate.line"
    _description = "WHT Certificate Line"

    certificate_id = fields.Many2one('account.wht.certificate', ondelete='cascade')
    invoice_move_id = fields.Many2one(
        'account.move',
        string='From Bill/Invoice',
        ondelete='set null',
        help='Source bill/invoice for this line (for multi-bill payment traceability)',
    )
    income_type_id = fields.Many2one('wht.income.type', string="Income Type")
    income_type_code = fields.Char(
        string="Income Type Code", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=False,
        help="Stored to preserve historical data"
    )
    income_type_name = fields.Char(
        string="Income Type Name", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=False,
        help="Stored to preserve historical data"
    )
    income_type_text = fields.Char(
        string="Legacy Income Type", 
        compute='_compute_income_type_fields', 
        store=True, 
        readonly=False
    )
    name = fields.Char(string="Name")
    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal')
    pay_date = fields.Date(string="Pay Date")
    base_amount = fields.Monetary(string="Base Amount")
    tax_amount = fields.Monetary(string="WHT Amount")
    currency_id = fields.Many2one(related='certificate_id.currency_id')

    @api.depends('income_type_id')
    def _compute_income_type_fields(self):
        for rec in self:
            if rec.income_type_id:
                rec.income_type_code = rec.income_type_id.code or ''
                rec.income_type_name = rec.income_type_id.name or ''
                rec.income_type_text = rec.income_type_id.name or ''
            else:
                if not rec.income_type_code:
                    rec.income_type_code = ''
                if not rec.income_type_name:
                    rec.income_type_name = ''
                if not rec.income_type_text:
                    rec.income_type_text = ''


def _default_wht_tax_group(self):
    return self.env["account.tax.group"].search([], limit=1)


class AccountWHT(models.Model):
    _name = "account.wht"
    _description = "Withholding Tax"

    name = fields.Char(string="Tax Name", required=True)
    tax_code = fields.Char(string="Tax Code")

    account_id = fields.Many2one(
        "account.account",
        string="WHT Account on Invoices",
        ondelete="restrict",
    )
    refund_account_id = fields.Many2one(
        "account.account", string="WHT Account on Credit Notes", ondelete="restrict"
    )
    income_type_id = fields.Many2one("wht.income.type", string="Income Type")
    description = fields.Text(string="Legacy Income Type")
    active = fields.Boolean(default=True)
    income_account_id = fields.Many2one("account.account", string="Income Account")
    expense_account_id = fields.Many2one("account.account", string="Expense Account")
    amount = fields.Float(string="Amount", required=True, digits=(16, 4), default=0.0)
    type_tax_use = fields.Selection(
        [
            ("sale", "Sales"),
            ("purchase", "Purchases"),
            ("none", "None"),
            ("tax", "Tax on Tax"),
        ],
        string="Tax Type",
        default="sale",
        required=True,
    )
    tax_application = fields.Selection(
        [("invoice", "Invoice"), ("payment", "Payment")],
        string="Tax Application",
        default="payment",
    )
    sale_tax_id = fields.Many2one("account.tax", string="Tax")
    wht_type = fields.Selection(
        [
            ('pnd1',         'ภ.ง.ด.1'),
            ('pnd1k',        'ภ.ง.ด.1ก'),
            ('pnd1_special', 'ภ.ง.ด.1 พิเศษ'),
            ('pnd2',         'ภ.ง.ด.2'),
            ('pnd2k',        'ภ.ง.ด.2ก'),
            ('pnd3',         'ภ.ง.ด.3'),
            ('pnd3k',        'ภ.ง.ด.3ก'),
            ('pnd53',        'ภ.ง.ด.53'),
        ],
        string="WHT Type",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    tax_group_id = fields.Many2one(
        "account.tax.group",
        string="Tax Group",
        default=_default_wht_tax_group,
        required=True,
    )

    @api.onchange("account_id")
    def onchange_account_id(self):
        self.refund_account_id = self.account_id
