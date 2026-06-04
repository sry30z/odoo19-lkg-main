# -*- coding: utf-8 -*-

"""

wht_calculation_service.py — Service Layer สำหรับการคำนวณ WHT (Withholding Tax)



บทบาทหลัก:

  - เป็น "จุดรวมศูนย์เดียว" (single source of truth) ของตรรกะทั้งหมดที่เกี่ยวกับ:

      • การค้นหาใบแจ้งหนี้ต้นทาง (bill discovery)

      • การบันทึก snapshot ข้อมูลพาร์ทเนอร์และเอกสาร ณ วันที่ชำระ

      • การสร้าง WHT detail lines (รองรับ partial-payment scaling)

      • การรวบรวม source line IDs เพื่อ full audit trail

  - ถูกเรียกใช้โดย AccountPayment._create_wht_certificate_after_payment_creation()

    ซึ่งทำหน้าที่เป็น orchestrator เท่านั้น (guards + idempotency + create)

  - ไม่ใช่ Odoo model — เป็น plain Python class เพื่อความเรียบง่ายและ testability

  - Stateless: รับ env ผ่าน constructor, ไม่เก็บ state ระหว่าง call



ใช้งาน:

    from .wht_calculation_service import WHTCalculationService

    service = WHTCalculationService(self.env)

    invoices     = service.discover_bills(wizard, payment)

    partner_snap = service.partner_snapshot(payment.partner_id)

    bill_snap    = service.bill_snapshot(invoices, payment)

    lines_vals   = service.build_detail_lines(wizard, invoices, payment)

    src_ids      = service.source_line_ids(invoices)

"""

import logging



_logger = logging.getLogger(__name__)





class WHTCalculationService:

    """

    Service Layer สำหรับการคำนวณ WHT (Withholding Tax)



    จุดรวมศูนย์สำหรับตรรกะทั้งหมดในการเตรียมข้อมูล WHT certificate:

      1. ค้นหาใบแจ้งหนี้ต้นทาง  (discover_bills)

      2. บันทึก snapshot พาร์ทเนอร์  (partner_snapshot)

      3. บันทึก snapshot ใบแจ้งหนี้  (bill_snapshot)

      4. สร้าง detail lines            (build_detail_lines)

      5. รวบรวม source line IDs        (source_line_ids)



    WHT Payment Ratio และ gross-up calculation ถูก handle โดย

    account.payment.register wizard ก่อนที่ service นี้จะถูกเรียกใช้

    ดังนั้น service นี้จึง**ไม่**คำนวณยอดเงินซ้ำ — ใช้ค่าจาก wizard.wht_line_ids โดยตรง

    """



    def __init__(self, env):

        self.env = env



    # ─────────────────────────────────────────────────────────────────────────

    # 0. Formula Engine — Single Source of Truth for ALL WHT calculations

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod

    def compute_wht_by_pay_type(amount, tax_rate, wht_pay_type):

        """

        Formula Engine — จุดคำนวณ WHT แบบรวมศูนย์เดียว (Single Source of Truth)



        Args:

            amount       (float): ยอดเงินต้นทาง (invoice line x payment ratio)

            tax_rate     (float): อัตราภาษีเป็น % เช่น 3.0 หมายถึง 3%

            wht_pay_type (str):   'normal' | 'gross_up_forever' | 'gross_up_once'



        Returns:

            dict with keys:

              base  — ฐานภาษีที่ใช้คำนวณ WHT

              wht   — จำนวนภาษีหัก ณ ที่จ่าย (rounded 2 dp)

              net   — ยอดสุทธิ์ที่ผู้รับบริการได้รับจริง

              total — ยอดรวมที่บริษัทจ่ายออก



        CASE 1 — หัก ณ ที่จ่าย (normal):

            base=amount, wht=base*rate, net=amount-wht, total=amount

            Example: amount=17500, rate=3% => base=17500 wht=525 net=16975



        CASE 2 — ออกให้ตลอด (gross_up_forever):

            gross_base=amount/(1-rate), wht=gross_base*rate, net=amount, total=gross_base

            Example: amount=17500, rate=3% => base=18041.24 wht=541.24 net=17500



        CASE 3 — ออกให้ครั้งเดียว (gross_up_once):

            base=amount (ไม่หาร 1-rate), wht=base*rate, net=amount, total=amount+wht

            Example: amount=17500, rate=3% => base=17500 wht=525 net=17500 total=18025

        """

        rate = tax_rate / 100.0



        if wht_pay_type == 'gross_up_forever':

            if abs(1.0 - rate) < 1e-9:

                raise ValueError(

                    "WHT rate cannot be 100%% for gross_up_forever "

                    "(tax_rate=%.4f%%)" % tax_rate

                )

            gross_base = amount / (1.0 - rate)

            wht        = round(gross_base * rate, 2)

            gross_base = round(gross_base, 2)

            return {'base': gross_base, 'wht': wht, 'net': amount, 'total': gross_base}



        elif wht_pay_type == 'gross_up_once':

            # ไม่หาร (1-rate) — ไม่ใช้ recursive gross-up

            wht   = round(amount * rate, 2)

            total = round(amount + wht, 2)

            return {'base': amount, 'wht': wht, 'net': amount, 'total': total}



        else:  # 'normal'

            wht = round(amount * rate, 2)

            return {'base': amount, 'wht': wht, 'net': round(amount - wht, 2), 'total': amount}





    # ─────────────────────────────────────────────────────────────────────────

    # 1. ค้นหาใบแจ้งหนี้ต้นทาง

    # ─────────────────────────────────────────────────────────────────────────

    def discover_bills(self, wizard, payment):

        """

        ค้นหาใบแจ้งหนี้ (vendor bills) ที่เชื่อมกับ payment นี้



        ลำดับความสำคัญของแหล่งข้อมูล:

          1. wizard.line_ids.mapped('move_id') — เชื่อถือได้มากที่สุด

             (wizard record ยังมีอยู่ใน request เดียวกัน, ไม่ต้องพึ่ง context)

          2. context.active_ids — fallback สำหรับ caller พิเศษที่ตั้ง active_ids เอง



        Args:

            wizard (account.payment.register): wizard ที่มี line_ids

            payment (account.payment): payment ที่กำลังประมวลผล



        Returns:

            account.move recordset: ใบแจ้งหนี้ที่เกี่ยวข้อง (อาจว่างเปล่าหากไม่พบ)

        """

        invoices = self.env['account.move']



        # ── แหล่งหลัก: wizard.line_ids ──

        if hasattr(wizard, 'line_ids') and wizard.line_ids:

            invoices = wizard.line_ids.mapped('move_id').filtered(

                lambda m: m.move_type in (

                    'in_invoice', 'out_invoice', 'in_refund', 'out_refund'

                ) and m.state == 'posted'

            )

            _logger.info(

                "[WHT SERVICE] พบ %d ใบแจ้งหนี้ จาก wizard.line_ids (payment=%s)",

                len(invoices), payment.name,

            )



        # ── Fallback: context.active_ids ──

        if not invoices:

            active_ids = payment.env.context.get('active_ids', [])

            active_model = payment.env.context.get('active_model', '')

            if active_ids:

                if active_model == 'account.move.line':

                    move_lines = self.env['account.move.line'].browse(active_ids).exists()

                    invoices = move_lines.mapped('move_id').filtered(

                        lambda m: m.move_type in (

                            'in_invoice', 'out_invoice', 'in_refund', 'out_refund'

                        )

                    )

                else:

                    invoices = self.env['account.move'].browse(active_ids).filtered(

                        lambda m: m.move_type in (

                            'in_invoice', 'out_invoice', 'in_refund', 'out_refund'

                        )

                    )

                if invoices:

                    _logger.info(

                        "[WHT SERVICE] พบ %d ใบแจ้งหนี้ จาก context.active_ids "

                        "(fallback, payment=%s)",

                        len(invoices), payment.name,

                    )



        if not invoices:

            _logger.warning(

                "[WHT SERVICE] ไม่พบใบแจ้งหนี้ต้นทางสำหรับ payment=%s — "

                "ใบรับรอง WHT จะถูกสร้างโดยไม่มีการเชื่อมใบแจ้งหนี้",

                payment.name,

            )



        return invoices



    # ─────────────────────────────────────────────────────────────────────────

    # 2. บันทึก snapshot ข้อมูลพาร์ทเนอร์

    # ─────────────────────────────────────────────────────────────────────────

    def partner_snapshot(self, partner):

        """

        บันทึก snapshot ข้อมูลพาร์ทเนอร์ ณ วันสร้างใบ WHT



        ป้องกันข้อมูลเปลี่ยนแปลงหลังสร้างใบรับรองแล้ว

        (กฎหมายภาษีไทย: ข้อมูลต้องถูกต้อง ณ วันที่จ่ายเงิน)



        Args:

            partner (res.partner | False): พาร์ทเนอร์ของ payment



        Returns:

            dict: field values สำหรับใส่ใน cert_vals โดยตรง

                  keys: partner_name_snapshot, partner_taxid, partner_address

        """

        if not partner:

            return {

                'partner_name_snapshot': '',

                'partner_taxid':         '',

                'partner_address':       '',

            }



        name_snap  = partner.name or ''

        taxid_snap = partner.vat or ''



        address_snap = ''

        try:

            address_snap = partner._display_address(without_company=True)

        except Exception as e:

            _logger.exception("[WHT SERVICE] Error getting partner address: %s", str(e))

            # fallback: ต่อ field ที่มีค่าเข้าด้วยกัน

            address_snap = ', '.join(filter(None, [

                partner.street,

                partner.street2,

                partner.city,

                partner.state_id.name if partner.state_id else '',

                partner.zip,

                partner.country_id.name if partner.country_id else '',

            ]))



        return {

            'partner_name_snapshot': name_snap,

            'partner_taxid':         taxid_snap,

            'partner_address':       address_snap,

        }



    # ─────────────────────────────────────────────────────────────────────────

    # 3. บันทึก snapshot ข้อมูลใบแจ้งหนี้

    # ─────────────────────────────────────────────────────────────────────────

    def bill_snapshot(self, invoices, payment):

        """

        บันทึก snapshot เลขที่ใบแจ้งหนี้, วันที่, และชื่อบริษัท ณ วันสร้างใบ WHT



        Args:

            invoices (account.move recordset): ใบแจ้งหนี้ที่เกี่ยวข้อง

            payment  (account.payment): payment ที่กำลังประมวลผล (fallback date/ref)



        Returns:

            dict: field values สำหรับใส่ใน cert_vals โดยตรง

                  keys: bill_reference_snapshot, invoice_date_snapshot,

                        branch_snapshot, wht_reference

        """

        bill_names = sorted(

            inv.name for inv in invoices

            if inv.name and inv.name not in ('New', '/', False)

        )

        bill_ref = (

            ', '.join(bill_names) if bill_names

            else (payment.ref or payment.name or '')

        )



        invoice_dates = sorted(inv.invoice_date for inv in invoices if inv.invoice_date)

        inv_date_snap = invoice_dates[0] if invoice_dates else payment.date



        branch_snap = payment.env.company.name or ''



        return {

            'bill_reference_snapshot': bill_ref,

            'invoice_date_snapshot':   inv_date_snap,

            'branch_snapshot':         branch_snap,

            'wht_reference':           bill_ref,

        }



    # ─────────────────────────────────────────────────────────────────────────

    # 4. สร้าง WHT detail lines

    # ─────────────────────────────────────────────────────────────────────────

    def build_detail_lines(self, wizard, invoices, payment):

        """

        สร้าง WHT certificate detail lines จาก wizard lines + ใบแจ้งหนี้



        กลยุทธ์:

          • wizard.wht_line_ids คือแหล่งข้อมูลที่เชื่อถือได้ (authoritative) สำหรับยอดเงิน

            (คำนวณโดย register wizard แล้ว รวม partial-payment scaling และ gross-up)

          • ใบแจ้งหนี้ใช้เพื่อ traceability เท่านั้น (invoice_move_id ในแต่ละบรรทัด)

          • หลายใบแจ้งหนี้: ใช้ใบแรกที่มี WHT tax นั้น ๆ

          • ใบแจ้งหนี้เดียว: เชื่อมทุกบรรทัดกับใบนั้น

          • บรรทัดเรียงตามลำดับ wizard (ไม่มีการสับเปลี่ยน)



        Args:

            wizard   (account.payment.register): wizard ที่มี wht_line_ids

            invoices (account.move recordset): ใบแจ้งหนี้ต้นทาง

            payment  (account.payment): payment (ใช้ date)



        Returns:

            list[tuple]: ORM command tuples [(0, 0, vals), ...]

        """

        if not wizard or not wizard.wht_line_ids:

            return []



        # สร้าง map {wht_id: [invoice, ...]} สำหรับ traceability

        bill_wht_map = {}

        for inv in sorted(invoices, key=lambda x: (x.invoice_date or '', x.name or '', x.id)):

            for line in sorted(inv.invoice_line_ids, key=lambda x: x.sequence):

                for wht in self._get_wht_taxes_from_invoice_line(line):

                    bill_wht_map.setdefault(wht.id, [])

                    if inv not in bill_wht_map[wht.id]:

                        bill_wht_map[wht.id].append(inv)



        lines_vals = []

        for w_line in wizard.wht_line_ids:

            wht = w_line.wht_id



            # best-effort: หาใบแจ้งหนี้ที่มี WHT นี้

            source_bills = bill_wht_map.get(wht.id, []) if wht else []

            if not source_bills and len(invoices) == 1:

                source_bills = list(invoices)

            source_invoice = source_bills[0] if source_bills else False



            lines_vals.append((0, 0, {

                'income_type_id':  wht.income_type_id.id if wht and wht.income_type_id else False,

                'name':            w_line.name or (wht.name if wht else ''),

                'base_amount':     w_line.base_amount,

                'tax_amount':      w_line.amount,

                'wht_pay_type':    wizard.wht_pay_type or 'normal',

                'pay_date':        payment.date,

                'invoice_move_id': source_invoice.id if source_invoice else False,

            }))



        return lines_vals



    # ─────────────────────────────────────────────────────────────────────────

    # 5. รวบรวม source line IDs สำหรับ audit trail

    # ─────────────────────────────────────────────────────────────────────────

    def source_line_ids(self, invoices):

        """

        รวบรวม invoice line IDs จากใบแจ้งหนี้ทั้งหมดเพื่อ full audit trail



        Args:

            invoices (account.move recordset): ใบแจ้งหนี้ต้นทาง



        Returns:

            list[int]: invoice line IDs ทั้งหมด

        """

        ids = []

        for inv in invoices:

            ids.extend(inv.invoice_line_ids.ids)

        return ids



    # ─────────────────────────────────────────────────────────────────────────

    # Helper: ดึง account.wht records จาก invoice line

    # ─────────────────────────────────────────────────────────────────────────

    def _get_wht_taxes_from_invoice_line(self, line):

        """

        คืนค่า list ของ account.wht records ที่เชื่อมกับ invoice line



        รองรับ 2 รูปแบบการเชื่อมโยงที่ module นี้ใช้:

          1. wht_tax_ids field โดยตรง (แนะนำ — Many2many บน invoice line)

          2. ค้นหา account.wht ผ่าน sale_tax_id (legacy style)



        Args:

            line (account.move.line): invoice line ที่ต้องการตรวจสอบ



        Returns:

            list[account.wht]: WHT records (อาจว่างเปล่า)

        """

        if not line:

            return []



        # Style 1: wht_tax_ids field โดยตรง

        if 'wht_tax_ids' in line._fields and line.wht_tax_ids:

            return list(line.wht_tax_ids)



        # Style 2: ค้นหา account.wht ผ่าน sale_tax_id (legacy)

        if line.tax_ids:

            all_wht = self.env['account.wht'].search(

                [('tax_application', '=', 'payment')]

            )

            wht_by_tax = {w.sale_tax_id.id: w for w in all_wht if w.sale_tax_id}

            return [wht_by_tax[t.id] for t in line.tax_ids if t.id in wht_by_tax]



        return []

