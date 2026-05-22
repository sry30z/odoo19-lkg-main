from odoo import fields, models, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_wht_base = fields.Monetary(string='WHT Base', compute='_compute_wht_totals', store=True)
    amount_wht = fields.Monetary(string='WHT Amount', compute='_compute_wht_totals', store=True)
    amount_net_total = fields.Monetary(string='Net Total', compute='_compute_wht_totals', store=True)
    wht_pay_type = fields.Selection([
        ('normal', 'หัก ณ จ่าย'),
        ('gross_up_forever', 'ออกให้ตลอด'),
        ('gross_up_once', 'ออกให้ครั้งเดียว'),
    ], string='WHT Pay Type', default='normal')

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['wht_pay_type'] = self.wht_pay_type
        return invoice_vals



    @api.depends('order_line.price_subtotal', 'order_line.wht_tax_ids', 'amount_total', 'wht_pay_type')
    def _compute_wht_totals(self):
        for order in self:
            wht_base_total = 0.0
            wht_amount_total = 0.0
            for line in order.order_line:
                if line.wht_tax_ids:
                    for wht in line.wht_tax_ids:
                        rate = wht.amount / 100.0
                        if order.wht_pay_type == 'gross_up_forever':
                            if abs(1 - rate) < 1e-9:
                                raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % wht.name)
                            base = line.price_subtotal / (1 - rate)
                        elif order.wht_pay_type == 'gross_up_once':
                            base = line.price_subtotal * (1 + rate)
                        else:
                            base = line.price_subtotal
                        
                        wht_base_total += base
                        wht_amount_total += round(base * rate, 2)
            
            order.amount_wht_base = wht_base_total
            order.amount_wht = wht_amount_total
            if order.wht_pay_type in ['gross_up_forever', 'gross_up_once']:
                order.amount_net_total = order.amount_total
            else:
                order.amount_net_total = order.amount_total - wht_amount_total


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    wht_tax_ids = fields.Many2many(
        'account.wht',
        string='WHT'
    )
    wht_id = fields.Many2one('account.wht', string='WHT ID')
    wht_rate = fields.Float(string='WHT Rate', related='wht_id.amount', readonly=True)
    wht_amount = fields.Monetary(string='WHT Amount', compute='_compute_wht_line_amount', store=True)
    wht_type = fields.Selection(related='wht_id.wht_type', string='WHT Type', readonly=True)

    @api.depends('price_subtotal', 'wht_id', 'wht_tax_ids', 'order_id.wht_pay_type')
    def _compute_wht_line_amount(self):
        for line in self:
            wht_amount = 0.0
            pay_type = line.order_id.wht_pay_type
            if line.wht_id or line.wht_tax_ids:
                taxes = line.wht_id | line.wht_tax_ids
                for wht in taxes:
                    rate = wht.amount / 100.0
                    if pay_type == 'gross_up_forever':
                        if abs(1 - rate) < 1e-9:
                            raise UserError(_("WHT rate cannot be 100%% for gross-up forever calculation (tax: %s).") % wht.name)
                        base = line.price_subtotal / (1 - rate)
                    elif pay_type == 'gross_up_once':
                        base = line.price_subtotal * (1 + rate)
                    else:
                        base = line.price_subtotal
                    wht_amount += round(base * rate, 2)
            line.wht_amount = wht_amount


    @api.onchange('wht_id')
    def _onchange_wht_id(self):
        if self.wht_id:
            self.wht_tax_ids = [(6, 0, [self.wht_id.id])]
        else:
            self.wht_tax_ids = [(5, 0, 0)]


    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        if self.wht_tax_ids:
            res.update({
                'wht_tax_ids': [(6, 0, self.wht_tax_ids.ids)],
                'wht_id': self.wht_id.id,
                'wht_amount': self.wht_amount,
            })
        return res

