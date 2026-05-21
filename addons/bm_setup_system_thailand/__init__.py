# -*- coding: utf-8 -*-
# See LICENSE file for full licensing details.
# See COPYRIGHT file for full copyright details.
# Developed by Bizmate - Unbox Solutions Co., Ltd.

from odoo.modules.module import get_resource_path
from odoo import _
from odoo.exceptions import ValidationError
import base64

def check_partner_country(env):
    partner = env['res.partner'].browse(env.ref('base.main_partner').id)
    if partner.country_id != env['res.country'].browse(env.ref('base.th').id):
        raise ValidationError(_("You do not set company's country to Thailand, Please change it first and install our module again."))


def activate_th_language(env):

    # Update Partner
    partner = env['res.partner'].browse(env.ref('base.main_partner').id)
    partner.country_id = env['res.country'].browse(env.ref('base.th').id).id
    
    # Auto Add Fiscal Localization Package Thailand
    company = env['res.company'].browse(env.ref('base.main_company').id)

    # Activate l10n_th Account Chart Template
    env['account.chart.template']._load('th', company=company, install_demo=False)

    # Language: EN (Flag Image)
    en_file_path = get_resource_path('bm_setup_system_thailand', 'static/img', 'en.png')
    en_lang = env['res.lang'].browse(env.ref('base.lang_en').id)
    if en_lang:
        en_lang.flag_image = base64.b64encode(open(en_file_path, 'rb').read())
    
    # Language: TH (Active + Flag Image)
    th_lang = env['res.lang'].browse(env.ref('base.lang_th').id)
    th_lang.active = True
    th_file_path = get_resource_path('bm_setup_system_thailand', 'static/img', 'th.png')
    th_lang.flag_image = base64.b64encode(open(th_file_path, 'rb').read())
    
    # Load Thai Language Translation
    mods = env['ir.module.module'].search([('state', '=', 'installed')])
    mods._update_translations('th_TH', True)

    # Update Thai Province Name
    env['res.country.state'].browse(env.ref('base.state_th_001').id).with_context(lang='th_TH').write({'name': 'กรุงเทพมหานคร'})
    env['res.country.state'].browse(env.ref('base.state_th_002').id).with_context(lang='th_TH').write({'name': 'อำนาจเจริญ'})
    env['res.country.state'].browse(env.ref('base.state_th_003').id).with_context(lang='th_TH').write({'name': 'อ่างทอง'})
    env['res.country.state'].browse(env.ref('base.state_th_004').id).with_context(lang='th_TH').write({'name': 'บึงกาฬ'})
    env['res.country.state'].browse(env.ref('base.state_th_005').id).with_context(lang='th_TH').write({'name': 'บุรีรัมน์'})
    env['res.country.state'].browse(env.ref('base.state_th_006').id).with_context(lang='th_TH').write({'name': 'ฉะเชิงเทรา'})
    env['res.country.state'].browse(env.ref('base.state_th_007').id).with_context(lang='th_TH').write({'name': 'ชัยนาท'})
    env['res.country.state'].browse(env.ref('base.state_th_008').id).with_context(lang='th_TH').write({'name': 'ชัยภูมิ'})
    env['res.country.state'].browse(env.ref('base.state_th_009').id).with_context(lang='th_TH').write({'name': 'จันทบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_010').id).with_context(lang='th_TH').write({'name': 'เชียงใหม่'})
    env['res.country.state'].browse(env.ref('base.state_th_011').id).with_context(lang='th_TH').write({'name': 'เชียงราย'})
    env['res.country.state'].browse(env.ref('base.state_th_012').id).with_context(lang='th_TH').write({'name': 'ชลบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_013').id).with_context(lang='th_TH').write({'name': 'ชุมพร'})
    env['res.country.state'].browse(env.ref('base.state_th_014').id).with_context(lang='th_TH').write({'name': 'กาฬสินธุ์'})
    env['res.country.state'].browse(env.ref('base.state_th_015').id).with_context(lang='th_TH').write({'name': 'กำแพงเพชร'})
    env['res.country.state'].browse(env.ref('base.state_th_016').id).with_context(lang='th_TH').write({'name': 'กาญจนบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_017').id).with_context(lang='th_TH').write({'name': 'ขอนแก่น'})
    env['res.country.state'].browse(env.ref('base.state_th_018').id).with_context(lang='th_TH').write({'name': 'กระบี่'})
    env['res.country.state'].browse(env.ref('base.state_th_019').id).with_context(lang='th_TH').write({'name': 'ลำปาง'})
    env['res.country.state'].browse(env.ref('base.state_th_020').id).with_context(lang='th_TH').write({'name': 'ลำพูน'})
    env['res.country.state'].browse(env.ref('base.state_th_021').id).with_context(lang='th_TH').write({'name': 'เลย'})
    env['res.country.state'].browse(env.ref('base.state_th_022').id).with_context(lang='th_TH').write({'name': 'ลพบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_023').id).with_context(lang='th_TH').write({'name': 'แม่ฮ่องสอน'})
    env['res.country.state'].browse(env.ref('base.state_th_024').id).with_context(lang='th_TH').write({'name': 'มหาสารคาม'})
    env['res.country.state'].browse(env.ref('base.state_th_025').id).with_context(lang='th_TH').write({'name': 'มุกดาหาร'})
    env['res.country.state'].browse(env.ref('base.state_th_026').id).with_context(lang='th_TH').write({'name': 'นครนายก'})
    env['res.country.state'].browse(env.ref('base.state_th_027').id).with_context(lang='th_TH').write({'name': 'นครปฐม'})
    env['res.country.state'].browse(env.ref('base.state_th_028').id).with_context(lang='th_TH').write({'name': 'นครพนม'})
    env['res.country.state'].browse(env.ref('base.state_th_029').id).with_context(lang='th_TH').write({'name': 'นครราชสีมา'})
    env['res.country.state'].browse(env.ref('base.state_th_030').id).with_context(lang='th_TH').write({'name': 'นครสวรรค์'})
    env['res.country.state'].browse(env.ref('base.state_th_031').id).with_context(lang='th_TH').write({'name': 'นครศรีธรรมราช'})
    env['res.country.state'].browse(env.ref('base.state_th_032').id).with_context(lang='th_TH').write({'name': 'น่าน'})
    env['res.country.state'].browse(env.ref('base.state_th_033').id).with_context(lang='th_TH').write({'name': 'นราธิวาส'})
    env['res.country.state'].browse(env.ref('base.state_th_034').id).with_context(lang='th_TH').write({'name': 'หนองบัวลำพู'})
    env['res.country.state'].browse(env.ref('base.state_th_035').id).with_context(lang='th_TH').write({'name': 'หนองคาย'})
    env['res.country.state'].browse(env.ref('base.state_th_036').id).with_context(lang='th_TH').write({'name': 'นนทบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_037').id).with_context(lang='th_TH').write({'name': 'ปทุมธานี'})
    env['res.country.state'].browse(env.ref('base.state_th_038').id).with_context(lang='th_TH').write({'name': 'ปัตตานี'})
    env['res.country.state'].browse(env.ref('base.state_th_039').id).with_context(lang='th_TH').write({'name': 'พังงา'})
    env['res.country.state'].browse(env.ref('base.state_th_040').id).with_context(lang='th_TH').write({'name': 'พัทลุง'})
    env['res.country.state'].browse(env.ref('base.state_th_041').id).with_context(lang='th_TH').write({'name': 'พะเยา'})
    env['res.country.state'].browse(env.ref('base.state_th_042').id).with_context(lang='th_TH').write({'name': 'เพชรบูรณ์'})
    env['res.country.state'].browse(env.ref('base.state_th_043').id).with_context(lang='th_TH').write({'name': 'เพชรบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_044').id).with_context(lang='th_TH').write({'name': 'พิจิตร'})
    env['res.country.state'].browse(env.ref('base.state_th_045').id).with_context(lang='th_TH').write({'name': 'พิษณุโลก'})
    env['res.country.state'].browse(env.ref('base.state_th_046').id).with_context(lang='th_TH').write({'name': 'พระนครศรีอยุธยา'})
    env['res.country.state'].browse(env.ref('base.state_th_047').id).with_context(lang='th_TH').write({'name': 'แพร่'})
    env['res.country.state'].browse(env.ref('base.state_th_048').id).with_context(lang='th_TH').write({'name': 'ภูเก็ต'})
    env['res.country.state'].browse(env.ref('base.state_th_049').id).with_context(lang='th_TH').write({'name': 'ปราจีนบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_050').id).with_context(lang='th_TH').write({'name': 'ประจวบคีรีขันธ์'})
    env['res.country.state'].browse(env.ref('base.state_th_051').id).with_context(lang='th_TH').write({'name': 'ระนอง'})
    env['res.country.state'].browse(env.ref('base.state_th_052').id).with_context(lang='th_TH').write({'name': 'ราชบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_053').id).with_context(lang='th_TH').write({'name': 'ระยอง'})
    env['res.country.state'].browse(env.ref('base.state_th_054').id).with_context(lang='th_TH').write({'name': 'ร้อยเอ็ด'})
    env['res.country.state'].browse(env.ref('base.state_th_055').id).with_context(lang='th_TH').write({'name': 'สระแก้ว'})
    env['res.country.state'].browse(env.ref('base.state_th_056').id).with_context(lang='th_TH').write({'name': 'สกลนคร'})
    env['res.country.state'].browse(env.ref('base.state_th_057').id).with_context(lang='th_TH').write({'name': 'สมุทรปราการ'})
    env['res.country.state'].browse(env.ref('base.state_th_058').id).with_context(lang='th_TH').write({'name': 'สมุทรสาคร'})
    env['res.country.state'].browse(env.ref('base.state_th_059').id).with_context(lang='th_TH').write({'name': 'สมุทรสงคราม'})
    env['res.country.state'].browse(env.ref('base.state_th_060').id).with_context(lang='th_TH').write({'name': 'สระบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_061').id).with_context(lang='th_TH').write({'name': 'สตูล'})
    env['res.country.state'].browse(env.ref('base.state_th_062').id).with_context(lang='th_TH').write({'name': 'สิงห์บุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_063').id).with_context(lang='th_TH').write({'name': 'ศรีสะเกษ'})
    env['res.country.state'].browse(env.ref('base.state_th_064').id).with_context(lang='th_TH').write({'name': 'สงขลา'})
    env['res.country.state'].browse(env.ref('base.state_th_065').id).with_context(lang='th_TH').write({'name': 'สุโขทัย'})
    env['res.country.state'].browse(env.ref('base.state_th_066').id).with_context(lang='th_TH').write({'name': 'สุพรรณบุรี'})
    env['res.country.state'].browse(env.ref('base.state_th_067').id).with_context(lang='th_TH').write({'name': 'สุราษฎร์ธานี'})
    env['res.country.state'].browse(env.ref('base.state_th_068').id).with_context(lang='th_TH').write({'name': 'สุรินทร์'})
    env['res.country.state'].browse(env.ref('base.state_th_069').id).with_context(lang='th_TH').write({'name': 'ตาก'})
    env['res.country.state'].browse(env.ref('base.state_th_070').id).with_context(lang='th_TH').write({'name': 'ตรัง'})
    env['res.country.state'].browse(env.ref('base.state_th_071').id).with_context(lang='th_TH').write({'name': 'ตราด'})
    env['res.country.state'].browse(env.ref('base.state_th_072').id).with_context(lang='th_TH').write({'name': 'อุบลราชธานี'})
    env['res.country.state'].browse(env.ref('base.state_th_073').id).with_context(lang='th_TH').write({'name': 'อุดรธานี'})
    env['res.country.state'].browse(env.ref('base.state_th_074').id).with_context(lang='th_TH').write({'name': 'อุทัยธานี'})
    env['res.country.state'].browse(env.ref('base.state_th_075').id).with_context(lang='th_TH').write({'name': 'อุตรดิตถ์'})
    env['res.country.state'].browse(env.ref('base.state_th_076').id).with_context(lang='th_TH').write({'name': 'ยะลา'})
    env['res.country.state'].browse(env.ref('base.state_th_077').id).with_context(lang='th_TH').write({'name': 'ยโสธร'})
    