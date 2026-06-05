# Thai WHT Certificate Recovery Guide
# คู่มือการกู้คืนใบรับหัก ณ ที่จ่ายที่หายไป

## 1. ภาพระบท (Overview)

### ปัญหา (Problem)
ใบรับหัก ณ ที่จ่ายบางใบอาจหายไปจาก trigger architecture ที่เสีย ในอดีต เนื่องจาก:
- การแก้ไขโค้ดที่ผิดพลาด
- การ deploy version เก่า
- การรีสตาร์ service ที่ไม่สมบูณ
- การยกเลิก server โดยไม่ตั้งค่า

### วัตถุ (Objective)
ค้นหาและสร้างใบรับหัก ณ ที่จ่ายที่หายไปอย่างปลอดภัยสำหรับ production accounting data

---

## 2. Execution Guide (วิธีการดำเนินการ)

### 2.1 Pre-Execution Checklist (รายการตรวจสอบก่อนรัน)

#### ✅ Database Backup
```bash
# 1. หยุด Odoo services
sudo systemctl stop odoo

# 2. Backup database
pg_dump -U odoo -d odoo18 -F c > backup_$(date +%Y%m%d_%H%M%S).sqlc
pg_dump -U odoo -d odoo18 -F d > backup_$(date +%Y%m%d_%H%M%S).dump

# 3. Filestore backup (ถ้าจำเป็น)
cp -r /var/lib/odoo/filestore /backup/filestore_$(date +%Y%m%d_%H%M%S)

# 4. เริ่มเปิด Odoo services
sudo systemctl start odoo
```

#### ✅ Environment Verification
```python
# ตรวจสอบ Odoo version และ Python version
python --version
odoo-bin --version

# ตรวจสอบ module account_WHT ถูกติดตั้ง
odoo-bin -c odoo.conf --list-modules | grep account_WHT
```

#### ✅ Code Deployment
```bash
# Deploy recovery script และ dependencies
# ตรวจสอบว่า script อยู่ที่ถูกต้อง
ls -la addons/account_WHT/scripts/recover_historical_wht_certificates.py
```

### 2.2 Step-by-Step Execution (ขั้นตอนการดำเนินการ)

#### Step 1: Dry-Run (การทดสอบแบบจำลอง)
```bash
# รันใน dry-run mode เพื่อดูผลล่วงหน้า
odoo-bin -c odoo.conf -d odoo18 --script-path addons/account_WHT/scripts/recover_hostorical_wht_certificates.py \
  --dry-run \
  --from-date 2024-01-01 \
  --to-date 2024-12-31
```

#### Step 2: Review Dry-Run Results
```bash
# ตรวจสอบ log file
tail -100 wht_recovery.log

# ตรวจสอบสถิติ:
- Payments scanned: จำนวนที่ถูก scan
- Payments eligible: จำนวนที่ตรงตามเงื่อนไข
- Existing certificates: จำนวนใบรับที่มีอยู่แล้ว
- Certificates created: จำนวนที่จะถูกสร้าง (ใน dry-run mode)
```

#### Step 3: Small Batch Test (การทดสอบ batch เล็ก)
```bash
# รันการกู้คืนเฉพาะ 10 payments แรกแรกครั้ง
odoo-bin -c odoo.conf -d odoo18 --script-path addons/account_WHT/scripts/recover_historical_wht_certificates.py \
  --batch-size 10 \
  --payment-ids 123,456,789  # ใส่ payment IDs ที่ต้องการทดสอบ
```

#### Step 4: Full Production Run (การรันใน Production)
```bash
# รันการกู้คืนสำหรับทั้งหมด ตามช่วงเวลาที่ต้องการ
odoo-bin -c odoo.conf -d odoo18 --script-path addons/account_WHT/scripts/recover_hostorical_wht_certificates \
  --batch-size 100 \
  --from-date 2024-01-01 \
  --to-date 2024-12-31
```

#### Step 5: Verify Results (การตรวจสอบผลล)
```bash
# ตรวจสอบ logs
tail -500 wht_recovery.log | grep "SUCCESS"

# ตรวจสอบ certificates ที่ถูกสร้างใน Odoo
# เข้าไปที่ Accounting → WHT Certificates
# ตรวจสอบว่า certificates ที่ถูกสร้างมีเลขบ้านถูกต้อง
```

---

## 3. Rollback Strategy (กลยุทศาลการ)

### 3.1 Rollback Scenarios (สถานการที่ต้อง Rollback)

#### Scenario 1: Certificate สร้างผิดพลาด
```python
# Action: Cancel certificates ที่ถูกสร้างโดย script
# Method 1: ผ่านที่สุด - Cancel ผ่าน automation
certificates_to_cancel = env['account.wht.certificate'].search([
    ('create_date', '>=', '<recovery_date>'),
    ('create_uid', '=', 1)  # Assuming script run by admin
])
certificates_to_cancel.action_cancel()

# Method 2: ถ้าต้องการ selective cancel
# ใช้ UI และ cancel certificates ที่ผิดพลาดทีละ
```

#### Scenario 2: Script รันแล้วหยุด
```python
# Action: เช็ค database locks
# โดย SQL queries ตรวจสอบ locks
SELECT pid, usename, query, state 
FROM pg_stat_activity 
WHERE datname = 'odoo18' 
AND state != 'idle';

# Kill blocking queries ถ้าจำเป็น
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE pid = <blocking_pid>;
```

#### Scenario 3: Certificate duplicate ถูกสร้าง
```python
# Action: ตรวจสอบและลบ duplicate certificates
# ใช้ logic ที่มีอยู่ใน script อัตโนมาตรฐาน
# มี custom_key uniqueness constraint ช่วยป้องกัน duplicate
```

### 3.2 Rollback Procedure (ขั้นตอน Rollback)

```bash
# 1. หยุด script ถ้ากำลังทำงานอยู่
# (Ctrl+C หรือ kill process)

# 2. ตรวจสอบ certificates ที่ถูกสร้างในช่วงเวลา script ทำงาน
# ใน Odoo: Accounting → WHT Certificates → Filter by create date

# 3. Cancel certificates ที่ผิดพลาด
# เลือก certificates ที่ต้องการลบ → Action → Cancel

# 4. Restore database ถ้าจำเป็น
sudo systemctl stop odoo
dropdb odoo18
createdb odoo18
pg_restore -d odoo18 < backup_YYYYMMDD_HHMMSS.sqlc
sudo systemctl start odoo
```

### 3.3 Database-Level Rollback (Rollback ระดับ Database)

```sql
-- 1. ระบุ certificates ที่ถูกสร้างโดย script ในช่วงเวลาที่กำหนด
SELECT id, certificate_no, create_date, create_uid 
FROM account_wht_certificate 
WHERE create_date >= '2025-01-25 10:00:00'
  AND create_date <= '2025-01-25 11:00:00'
ORDER BY create_date;

-- 2. สร้าง table สำหรับ tracking (ถ้าจำเป็น)
CREATE TABLE recovery_tracking (
    id SERIAL PRIMARY KEY,
    certificate_id INTEGER,
    original_state VARCHAR(50),
    action_taken VARCHAR(50),
    timestamp TIMESTAMP DEFAULT NOW()
);

-- 3. Insert tracking records
INSERT INTO recovery_tracking (certificate_id, original_state, action_taken)
SELECT id, state, 'cancelled_by_recovery_script'
FROM account_wht_certificate
WHERE create_date >= '2025-01-25 10:00:00'
  AND create_date <= '2025-01-25 11:00:00';

-- 4. Cancel certificates
UPDATE account_wht_certificate
SET state = 'cancel'
WHERE create_date >= '2025-01-25 25 10:00:00'
  AND create_date <= '2025-01-25 11:00:00;
```

---

## 4. Validation Checklist (รายการตรวจสอบ)

### 4.1 Pre-Execution Validation (ตรวจสอบก่อนรัน)

- [ ] **Database backup ล่าสุด** - ต้อง backup ภายใน 24 ชั่วโมง
- [ ] **Odoo version ตรงกับ requirement** - Odoo 18+ สำหรับ Thai WHT module
- [ ] **Module account_WHT ถูกติดตั้ง** - ตรวจสอบ version และ state
- [ ] **Script อยู่ใน path ที่ถูกต้อง** - `addons/account_WHT/scripts/`
- [ ] **Log file path สามารถเขียนได้** - มี disk space เพียงพอ
- [ ] **User เป็น admin/ผู้มีสิทธิ** - ต้องมีสิทธิ access ในการสร้าง certificates
- [ ] **เช็ค system resources** - CPU, RAM, disk space เพียงพอ
- [ ] **เช็ค network connectivity** - ถ้าใช้ external services

### 4.2 Post-Execution Validation (ตรวจสอบหลังรัน)

- [ ] **Log ไม่มี ERROR critical** - ตรวจสอบ `wht_recovery.log`
- [ ] **Certificates ที่สร้างถูกตรวจสอบ** เข้า Odoo UI และตรวจ
- [ ] **Certificate numbers ถูก generate อย่างถูกต้อง** - format ถูกต้อง
- [ ] **Tax amounts ถูกคำนวณถูกต้อง** - cross-check กับ bills
- [ ] **Partner data ถูกกรอกถูกต้อง** - address, tax ID เป็นต้น
- [ ] **Accounting integrity ไม่ผิดพลาด** - balance ยังถูกต้อง
- [ ] **Reconciliation ไม่ถูกระทบ** - payment-bill reconciliation ยังถูกต้อง
- [ ] **Journal entries ถูกสร้างถูกต้อง** - ตรวจสอบใน Accounting → Journal Entries
- [ ] **No duplicate certificates** - ตรวจสอบว่าไม่มี certificate เดียวกัน

### 4.3 Data Integrity Checks (การตรวจสอบความสมบูร)

```sql
-- 1. ตรวจสอบ certificate vs payment amounts
SELECT 
    c.certificate_no,
    p.name as payment_name,
    c.amount as cert_amount,
    p.amount as payment_amount,
    c.amount - p.amount as difference
FROM account_wht_certificate c
JOIN account_payment p ON c.payment_id = p.id
WHERE c.create_date >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY ABS(c.amount - p.amount) DESC
LIMIT 10;

-- 2. ตรวจสอบ certificates ที่ไม่มี payment
SELECT id, certificate_no, partner_id, payment_id, state
FROM account_wht_certificate
WHERE payment_id IS NULL
AND state != 'cancel'
ORDER BY create_date DESC
LIMIT 10;

-- 3. ตรวจสอบ payments ที่ไม่มี certificate (eligible)
SELECT 
    p.name as payment_name,
    p.date,
    p.amount,
    p.partner_id,
    (SELECT COUNT(*) FROM account_wht_certificate 
     WHERE payment_id = p.id AND state != 'cancel') as cert_count
FROM account_payment p
WHERE p.state = 'posted'
  AND p.payment_type = 'outbound'
  AND p.partner_type = 'vendor'
ORDER BY p.date DESC
LIMIT 20;
```

---

## 5. Production Safety Notes (ข้อควรระวังความปลอดภัย)

### 5.1 Script Safety Features (คุณลักษณความปลอดของ Script)

#### ✅ Idempotency (ความสามารถรันซ้ำได้)
- Script ใช้ existing certificate check ป้องกันการสร้างซ้ำ
- รัน script หลายครั้งจะไม่สร้าง duplicate certificates
- ระบุ existing certificates โดย custom_key uniqueness constraint

#### ✅ Dry-Run Mode (โหมดแบจำลอง)
- Default behavior คือ dry-run
- จะแสดงผลล่วงหน้าโดยไม่สร้าง records
- เหมมการเปลี่ยนไป production mode โดยไม่ dry-run ก่อน

#### ✅ Batch Processing (การประมวลผลเป็น batch)
- Process payments 100 records ต่อ batch
- Commit หลัง batch เพื่อหลีก long transactions
- ช่วยลดลง risk ในกรณี failure

#### ✅ No State Modification (ไม่แก้ไข accounting state)
- ไม่แก้ไข payment states
- ไม่ alter reconciliation
- ไม่ลบ production records
- ใช้ ORM methods เท่านอย่างปลอดภัย

#### ✅ Comprehensive Logging (Logging ครอบคลุม)
- Log ทุก validation step
- Log ทุก certificate creation
- Log ทุก error พร้อม stack trace
- Generate summary report

### 5.2 Operational Safety (ความปลอดดำเนินงาน)

#### ✅ Maintenance Window (ช่วงเวลาทำงาน)
- ทำงานนอกชั่งเวลาที่ traffic ต่ำ
- แจ้ง users ว่ามีการบำรังฐานข้อมูล
- หลีกการทำงาน parallel ที่เกี่ยวกข้องเดียวกัน

#### ✅ User Communication (การสื่อสารกับ users)
- แจ้ง users ก่อนว่าจะมีการสร้าง certificates
- อธิบายว่า certificates ที่สร้างใหมความเสถาพ
- แจ้ง users ว่าการบำรังจะกระทบ workflow อย่างไร

#### ✅ Monitoring (การติดตามสถานะ)
- ติดตาม log file ใน real-time
- ติดตาม database size growth
- ติดตาม system resources ระหว่าง process

### 5.3 Data Privacy (ความเป็นส่วนตนข้อมูล)
- Logs ไม่มี sensitive data เช่น full VAT IDs
- ไม่เก็บข้อมูล personal identification
- ตรวจสอบว่า log files มี access permissions ถูกต้อง
- ลบหรัด log files หลังจากเวลาที่กำหนด

### 5.4 Permission Management (การจัดการสิทธิ)
- Script ต้องถูกรันโดย admin user
- ตรวจสอบว่า user มีสิทธิ create บน account.wht.certificate
- ตรวจสอบว่า user มีสิทธิ read บน account.payment
- Review access logs หลัง run script

---

## 6. Troubleshooting (การแก้ปัญหา)

### 6.1 Common Issues (ปัญหาที่พบบบ่อย)

#### Issue 1: Script ไม่สามารถ import Odoo
```
Error: This script must be run within Odoo environment
Solution: ใช้ odoo-bin --script-path แทนการรัน python script ตรงๆ
```

#### Issue 2: Certificate number generation fails
```
Error: Failed to generate certificate number
Solution: ตรวจสอบ sequence 'account.wht.certificate' ถูกตั้งค่าอย่างถูกต้อง
```

#### Issue 3: Reconciliation discovery returns no bills
```
Error: No reconciled bills found
Solution: ตรวจสอบว่า payment ถูก reconcile กับ bills จริง
```

#### Issue 4: Script hangs หรือช้า
```
Error: Script appears to be stuck
Solution: ตรวจสอบ database locks, ปรับ batch size ให้เล็กลง
```

#### Issue 5: Memory exhaustion
```
Error: Out of memory
Solution: ลด batch size ลง, process ใน batches ที่เล็กลง
```

### 6.2 Debug Commands (คำสั่ง debug)

```bash
# ตรวจสอบ script version
head -20 addons/account_WHT/scripts/recover_historical_wht_certificates.py

# ตรวจสอบ log file
tail -100 wht_recovery.log

# ตรวจสอบ recent certificate creations
psql -d odoo18 -c "SELECT id, certificate_no, create_date, create_uid FROM account_wht_certificate ORDER BY create_date DESC LIMIT 10"

# ตรวจสอบ database connections
psql -d odoo18 -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'odoo18'"
```

---

## 7. Success Criteria (เกณฑ์สำเร็จ)

### 7.1 Recovery Success Indicators (ตัวชี้ว่ากู้คืนสำเร็จ)
- ✅ Script รันสำเร็จโดยไม่มี critical errors
- ✅ Certificates ที่สร้างถูกตรวจสอบและถูกยืนยัน
- ✅ Certificate numbers ถูก generate ถูกต้อง
- ✅ Tax amounts ถูกคำนวณถูกต้อง
- ✅ Accounting balance ยังถูกต้องหลังสร้าง certificates
- ✅ Reconciliation ไม่ถูกกระทบ
- ✅ No duplicate certificates ถูกสร้าง

### 7.2 Success Metrics (ตัววัดผล)
- **Recovery Rate**: (Certificates created) / (Payments eligible) × 100%
- **Target**: > 95% ของ payments ที่ eligible ควรได้รับ certificates
- **Accuracy Rate**: Certificates ที่ถูกสร้างถูกตรวจสอบถูกต้อง
- **Target**: 100% ควรถูกตรวจสอบและ confirm ได้

---

## 8. Contact Support (ติดต่อ Support)

### 8.1 Emergency Contacts (ข้อมูลติดต่อฉุกเร่ง)
- **Database Admin**: [Contact details]
- **System Admin**: [Contact details]
- **Accounting Team**: [Contact details]
- **Odoo Developer**: [Contact details]

### 8.2 Incident Response (การตอบสนองเหตุการ)
1. หยุด script ทันทีถ้าพบ critical errors
2. ระบุ scope ของผลกระทบ
3. ตัดสินใจทันที: stop script, assess damage
4. แจ้ง stakeholders ทันที
5. Execute recovery plan (rollback หรือ proceed)

---

## 9. Appendix (ภาคผน

### 9.1 SQL Queries สำหรับ Monitoring

```sql
-- Query 1: Certificates สร้างโดย recovery script
SELECT 
    c.certificate_no,
    c.create_date,
    c.create_uid,
    p.name as payment_name,
    p.date as payment_date
FROM account_wht_certificate c
JOIN account_payment p ON c.payment_id = p.id
WHERE c.create_uid = 1  -- Assuming admin user ran the script
ORDER BY c.create_date DESC;

-- Query 2: Payments ที่ยังไม่มี certificate (หลัง recovery)
SELECT 
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

### 9.2 Script Parameters Reference

```bash
--dry-run              Preview changes without creating certificates
--from-date YYYY-MM-DD   Start date for scanning payments
--to-date YYYY-MM-DD     End date for scanning payments
--partner-ids 1,2,3     Specific partner IDs (comma-separated)
--payment-ids 1,2,3      Specific payment IDs (comma-separated)
--batch-size 100         Batch size for processing (default: 100)
```

---

**END OF GUIDE**
Version: 1.0
Last Updated: 2025-01-25
Author: Senior Odoo Accounting Recovery Engineer
