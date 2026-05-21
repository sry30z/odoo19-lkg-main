import odoo
from odoo import api, SUPERUSER_ID

def test_report():
    db = 'wht'
    registry = odoo.registry(db)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        cert = env['account.wht.certificate'].search([], limit=1)
        if not cert:
            print("No certificate found")
            return
        
        print(f"Generating report for certificate: {cert.certificate_no}")
        try:
            report = env.ref('account_WHT.action_wht_50tawi')
            pdf_content, _ = report._render_qweb_pdf(cert.id)
            print("Successfully generated PDF")
        except Exception as e:
            import traceback
            print(f"Error generating report: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    test_report()
