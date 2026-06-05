# WHT Certificate Recovery Validation Checklist
# รายการตรวจสอบกู้คืนใบรับหัก ณ ที่จ่าย

---

## 📋 Pre-Execution Checklist (ตรวจสอบก่อนรัน script)

### ✅ Database & Backup
- [ ] Database backup ล่าสุด (ภายใน 24 ชั่วโมง) พร้อม
- [ ] Backup file integrity verified (checksum ถูกต้อง)
- [ ] Filestore backup พร้อม (ถ้าจำเป็น)
- [ ] Database restore test ทำแล้ว (ถ้าจำเป็น)

### ✅ Environment & Dependencies
- [ ] Odoo version คือ 18+ สำหรับ Thai WHT module
- [ ] Python version คือ 3.10+ สำหรับ Odoo 18
- [ ] Module `account_WHT` ถูกติดตั้งและ active
- [ ] Module version matches requirement
- [ ] Dependencies ทั้งหมดถูกติดตั้ง (check pip list)

### ✅ Script & Configuration
- [ ] Recovery script อยู่ที่: `addons/account_WHT/scripts/recover_historical_wht_certificates.py`
- [ ] Script file permissions ถูกต้อง (executable)
- [ ] Script can be accessed โดย Odoo user
- [ ] Log file directory writable (`/var/log/odoo/` หรือที่เลือก)
- [ ] Disk space เพียงพอสำหรับ log files (ขั้นต่ำ 1GB)

### ✅ User Permissions
- [ ] Script will run as admin/superuser user
- [ ] User มีสิทธิ `create` บน `account.wht.certificate`
- [ ] User มีสิทธิ `read` บน `account.payment`
- [ ] User มีสิทธิ `read` บน `account.move`
- [ ] User มีสิทธิ `read` บน `account.wht.certificate`

### ✅ System Resources
- [ ] CPU utilization < 70% ก่อนรัน script
- [ ] RAM utilization < 80% ก่อนรัน script
- [ ] Disk space พร้อม อย่างน้อย 10GB
- [ ] Network connectivity stable ถ้าใช้ external services
- [ ] I/O performance adequate สำหรับ database operations

### ✅ Testing & Dry-Run
- [ ] Dry-run test ทำสำเร็จโดยไม่มี errors
- [ ] Dry-run results ถูกตรวจสอบและถูกต้อง
- [ ] Small batch test (10-50 payments) ทำสำเร็จ
- [ ] Sample certificates ถูกตรวจสอบถูกต้อง
- [ ] Manual verification เสร็จสมบูรณ์

### ✅ Communication
- [ ] Accounting team ได้รับแจ้งว่าจะมีการสร้าง certificates
- [ ] Operations team ได้รับแจ้งว่าจะมีการบำรัง database
- [ ] Users ได้รับแจ้งว่า workflow อาจมีผลกระทบชั่วคราว
- [ ] Maintenance window ถูกจัดไว้ (ถ้าจำเป็น)
- [ ] Rollback plan ได้รับการ approve

---

## 📋 Post-Execution Checklist (ตรวจสอบหลังรัน script)

### ✅ Script Execution Verification
- [ ] Script รันสำเร็จโดยไม่มี critical errors
- [ ] Log file ถูกสร้างและมีข้อมูลครบ
- [ ] Summary report ถูกสร้างและตรวจสอบ
- [ ] No unexpected exceptions ใน logs
- [ ] Batch processing สำเร็จทุก batch

### ✅ Certificate Creation Verification
- [ ] Certificates ที่สร้างถูกตรวจสอบใน Odoo UI
- [ ] Certificate numbers ถูก generate ถูกต้อง (format ถูกต้อง)
- [ ] Tax amounts ถูกคำนวณถูกต้อง
- [ ] Partner data ถูกกรอกถูกต้อง (address, tax ID, etc.)
- [ ] Certificate dates ถูกต้อง (payment dates)

### ✅ Accounting Integrity Verification
- [ ] Payment-Bill reconciliation ยังถูกต้อง
- [ ] Journal entries ถูกสร้างถูกต้อง
- [ ] Payment amounts ยังถูกต้อง
- [ ] Bill amounts ยังถูกต้อง
- [ ] Tax accounts ถูก debit/credit ถูกต้อง
- [ ] Balance sheet ยังถูกต้อง

### ✅ Duplicate Prevention Verification
- [ ] No duplicate certificates ถูกสร้าง
- [ ] Custom key uniqueness constraints ทำงานถูกต้อง
- [ ] Payment หนึ่งไม่มี > 1 certificate ที่ active
- [ ] Certificate numbers ไม่ duplicate
- [ ] Database foreign keys ยังถูกต้อง

### ✅ Data Quality Verification
- [ ] Certificate ที่สร้างมี payment references ถูกต้อง
- [ ] Certificate ที่สร้างมี partner references ถูกต้อง
- [ ] Certificate ที่สร้างมี amount references ถูกต้อง
- [ ] Certificate state = 'draft' หรือ 'confirmed' ตาม flow
- [ ] Certificate ที่สร้างสามารถ view ใน UI ได้

### ✅ Performance & System Verification
- [ ] Database performance ไม่ลดลงอย่างชัดเจน
- [ ] System resources กลับมา normal
- [ ] No long-running transactions ยังค้างอยู่
- [ ] No database locks ยังค้างอยู่
- [ ] No orphaned records ถูกสร้าง

---

## 📋 Data Integrity Verification (ตรวจสอบความสมบูร์ข้อมูล)

### ✅ Payment Certificate Mapping
- [ ] ตรวจสอบทุก payment ที่ถูก process มี certificate references
- [ ] ตรวจสอบ certificate ที่สร้างมี payment references ถูกต้อง
- [ ] ตรวจสอบ one-to-one mapping ถูกต้อง
- [ ] ตรวจสอบไม่มี payments ที่ orphan (no certificate)

### ✅ Amount Accuracy
- [ ] Certificate amount = Payment amount WHT portion
- [ ] Certificate ที่สร้างไม่ส่งผลกระทบ balance sheet
- [ ] Tax amounts ถูกคำนวณถูกต้องตาม tax rules
- [ ] Rounding ทำงานถูกต้อง

### ✅ Reconciliation Integrity
- [ ] Payment-Bill reconciliation ยังถูกต้อง
- [ ] No reconciliation records ถูกลบหรือแก้ไข
- [ ] Reconciliation dates ยังถูกต้อง
- [ ] Partial payments ถูกจัดการถูกต้อง

---

## 📋 SQL Validation Queries (SQL Queries สำหรับตรวจสอบ)

### Query 1: Certificates ที่สร้างโดย recovery script
```sql
SELECT 
    c.id,
    c.certificate_no,
    c.create_date,
    c.create_uid,
    p.name as payment_name,
    p.date as payment_date,
    c.amount,
    c.state
FROM account_wht_certificate c
JOIN account_payment p ON c.payment_id = p.id
WHERE c.create_date >= '2025-01-25 10:00:00'  -- ปรับ timestamp
ORDER BY c.create_date DESC
LIMIT 20;
```

### Query 2: Payments ที่ยังไม่มี certificate (หลัง recovery)
```sql
SELECT 
    p.id,
    p.name,
    p.date,
    p.amount,
    pp.name as partner_name,
    (SELECT COUNT(*) FROM account_wht_certificate 
     WHERE payment_id = p.id AND state != 'cancel') as cert_count
FROM account_payment p
JOIN res_partner pp ON p.partner_id = pp.id
WHERE p.state = 'posted'
  AND p.payment_type = 'outbound'
  AND p.partner_type = 'vendor'
  AND p.date >= '2024-01-01'
ORDER BY p.date DESC;
```

### Query 3: Certificate vs Payment Amount Discrepancies
```sql
SELECT 
    c.certificate_no,
    p.name as payment_name,
    c.amount as cert_amount,
    p.amount as payment_amount,
    ABS(c.amount - p.amount) as difference
FROM account_wht_certificate c
JOIN account_payment p ON c.payment_id = p.id
WHERE c.create_date >= '2025-01-25 10:00:00'
ORDER BY difference DESC
LIMIT 10;
```

### Query 4: Certificate Duplicate Detection
```sql
SELECT 
    certificate_no,
    COUNT(*) as duplicate_count,
    STRING_AGG(id::text, ', ') as certificate_ids
FROM account_wht_certificate
WHERE state != 'cancel'
GROUP BY certificate_no
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

### Query 5: Certificate State Distribution
```sql
SELECT 
    state,
    COUNT(*) as count,
    MIN(create_date) as first_created,
    MAX(create_date) as last_created
FROM account_wht_certificate
WHERE create_date >= '2025-01-25 10:00:00'
GROUP BY state
ORDER BY count DESC;
```

---

## 📋 Rollback Readiness Checklist (รายการตรวจสอบ Rollback)

### ✅ Rollback Verification
- [ ] Database backup พร้อม restore
- [ ] Restore procedure documented
- [ ] Rollback test done (ใน staging environment)
- [ ] Support team รับทราบ rollback plan
- [ ] Approval สำหรับ rollback พร้อม

### ✅ Rollback Execution (ถ้าจำเป็น)
- [ ] หยุด script ทันที (ถ้ายังทำงานอยู่)
- [ ] ระบุ scope ของผลกระทบ
- [ ] Execute restore ตาม procedure
- [ ] Verify data integrity หลัง restore
- [ ] แจ้ง stakeholders เสร็จสมบูรณ์

---

## 📋 Sign-Off (การลงลายมือชื่อ)

### Pre-Execution Approval
- **Database Admin**: _______________ Date: ________
- **System Admin**: _______________ Date: ________
- **Accounting Manager**: _______________ Date: ________
- **Odoo Developer**: _______________ Date: ________

### Post-Execution Validation
- **Database Admin**: _______________ Date: ________
- **System Admin**: _______________ Date: ________
- **Accounting Manager**: _______________ Date: ________
- **Odoo Developer**: _______________ Date: ________

### Rollback Approval (ถ้าจำเป็น)
- **Operations Manager**: _______________ Date: ________
- **Finance Director**: _______________ Date: ________
- **Technical Director**: _______________ Date: ________

---

**Notes:**
- ตรวจสอบทุก checklist item ก่อน execute หรือ approve
- ถ้า fail ใน checklist item ใด ต้อง resolve ก่อน proceed
- Document ทุก deviation หรือ exception ที่พบ
- Retain checklist records อย่างน้อย 1 year สำหรับ compliance

---

**END OF VALIDATION CHECKLIST**
Version: 1.0
Last Updated: 2025-01-25
