# -*- coding: utf-8 -*-
import odoo
from odoo import api, SUPERUSER_ID

def check_wht_system(env):
    print("==================================================")
    print("          DIAGNOSTIC WHT ACCUMULATION SYSTEM       ")
    print("==================================================")
    
    # 1. Check wht.income.type fields
    print("\n[1] Checking 'wht.income.type' model fields:")
    IncomeType = env['wht.income.type']
    fields_to_check = ['certificate_line_ids', 'total_base', 'total_tax']
    for field in fields_to_check:
        if field in IncomeType._fields:
            print(f"  - Field '{field}' exists in registry: YES (Type: {IncomeType._fields[field].type})")
        else:
            print(f"  - Field '{field}' exists in registry: NO!")
            
    # 2. Check wht.income.type records
    print("\n[2] Checking Income Types accumulated totals:")
    types = IncomeType.search([])
    for t in types:
        print(f"  - Code: {t.code} | Name: {t.name} | Total Base: {t.total_base:.2f} | Total Tax: {t.total_tax:.2f} | Active: {t.active}")
        
    # 3. Check account.wht.certificate.line fields
    print("\n[3] Checking 'account.wht.certificate.line' model computed fields:")
    CertLine = env['account.wht.certificate.line']
    fields_cert = ['income_type_code', 'income_type_name', 'income_type_text']
    for field in fields_cert:
        if field in CertLine._fields:
            f_obj = CertLine._fields[field]
            print(f"  - Field '{field}' exists: YES (Type: {f_obj.type}, Compute: {f_obj.compute}, Stored: {f_obj.store})")
        else:
            print(f"  - Field '{field}' exists: NO!")
            
    # 4. Check account.move.line fields
    print("\n[4] Checking 'account.move.line' sync fields:")
    MoveLine = env['account.move.line']
    if 'wht_tax_ids' in MoveLine._fields:
        f_obj = MoveLine._fields['wht_tax_ids']
        print(f"  - Field 'wht_tax_ids' exists: YES (Type: {f_obj.type}, Compute: {f_obj.compute}, Stored: {f_obj.store}, Readonly: {f_obj.readonly})")
    else:
        print(f"  - Field 'wht_tax_ids' exists: NO!")
        
    # 5. Check if there are active WHT Certificates
    print("\n[5] Checking active WHT Certificates:")
    certs = env['account.wht.certificate'].search([])
    print(f"  - Total WHT Certificates: {len(certs)}")
    for c in certs:
        print(f"    * Cert No: {c.certificate_no} | Date: {c.issue_date} | State: {c.state} | Base: {c.base_amount:.2f} | Tax: {c.tax_amount:.2f}")
        for l in c.line_ids:
            print(f"      - Line Name: {l.name} | Code: {l.income_type_code} | Name: {l.income_type_name} | Base: {l.base_amount:.2f} | Tax: {l.tax_amount:.2f}")

    print("\n==================================================")
    print("             DIAGNOSTIC COMPLETED                 ")
    print("==================================================")

if 'env' in locals() or 'env' in globals():
    check_wht_system(env)
else:
    # If run as standalone script outside odoo shell
    db = 'wht'
    registry = odoo.registry(db)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        check_wht_system(env)
