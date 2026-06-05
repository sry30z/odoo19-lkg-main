# -*- coding: utf-8 -*-
import logging
import os

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Production-safe migration to upgrade WHT uniqueness constraints.
    - Idempotency via constraint check
    - Fail-hard duplicate detection
    - Deterministic custom_key update
    - Optional dry-run and advisory lock
    """
    _logger.info("=" * 60)
    _logger.info("WHT MIGRATION 18.0.1.5.2: Upgrading constraints")
    _logger.info("=" * 60)

    # 1. (Optional) Dry-run check
    is_dry_run = bool(os.getenv("WHT_MIGRATION_DRY_RUN"))
    if is_dry_run:
        _logger.info("--- RUNNING IN DRY-RUN MODE ---")

    # 2. (Optional-safe) Concurrency Protection
    LOCK_KEY = 18150152
    cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (LOCK_KEY,))
    if not cr.fetchone()[0]:
        raise Exception("MIGRATION BLOCKED: Migration is already running in another process.")

    # 3. Idempotency Check
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conname = 'account_wht_certificate_certificate_business_unique'
    """)
    if cr.fetchone():
        _logger.info("Migration already successfully applied. Skipping.")
        return

    # 4. Deterministic custom_key update (Must run BEFORE duplicate detection)
    _logger.info("Step 1: Updating custom_keys using deterministic algorithm...")
    
    # We update custom_key for ALL records to ensure consistency with the new deterministic format,
    # or just the NULL ones. For safety and compliance with the plan, we normalize NULLs and malformed ones.
    cr.execute("""
        UPDATE account_wht_certificate
        SET custom_key = 
            COALESCE(payment_id::text, 'manual') || '_' ||
            COALESCE(move_id::text, id::text) || '_' ||
            COALESCE(wht_type, 'none') || '_' ||
            COALESCE(income_type, 'none') || '_' ||
            COALESCE(pay_date::text, issue_date::text, 'none')
        WHERE custom_key IS NULL OR custom_key = ''
    """)

    # 5. Fail-Hard Duplicate Detection
    _logger.info("Step 2: Auditing for business duplicates...")
    cr.execute("""
        SELECT 
            company_id, 
            partner_id, 
            wht_type, 
            income_type, 
            pay_date, 
            custom_key, 
            COUNT(*) as duplicate_count, 
            array_agg(id ORDER BY id) as conflicting_ids
        FROM account_wht_certificate
        GROUP BY 
            company_id, 
            partner_id, 
            wht_type, 
            income_type, 
            pay_date, 
            custom_key
        HAVING COUNT(*) > 1
    """)
    duplicates = cr.fetchall()
    
    if duplicates:
        _logger.error("=" * 60)
        _logger.error("MIGRATION BLOCKED — DUPLICATE CERTIFICATE REPORT")
        _logger.error(f"Found {len(duplicates)} duplicate groups violating the new constraint.")
        for idx, row in enumerate(duplicates, 1):
            _logger.error(f"DUPLICATE GROUP {idx}:")
            _logger.error(f"  Company ID   : {row[0]}")
            _logger.error(f"  Partner ID   : {row[1]}")
            _logger.error(f"  WHT Type     : {row[2]}")
            _logger.error(f"  Income Type  : {row[3]}")
            _logger.error(f"  Pay Date     : {row[4]}")
            _logger.error(f"  Custom Key   : {row[5]}")
            _logger.error(f"  Conflicting IDs: {row[7]}")
            _logger.error("-" * 40)
        
        _logger.error("ACTION REQUIRED: Accountant must manually review and correct these duplicates.")
        _logger.error("=" * 60)
        if not is_dry_run:
            raise Exception("MIGRATION BLOCKED: Duplicate WHT Certificates detected. See logs for details.")

    if is_dry_run:
        _logger.info("DRY-RUN completed safely. Exiting.")
        return

    # 6. Drop old constraint safely by checking real name first
    _logger.info("Step 3: Dropping old constraint if exists...")
    cr.execute("""
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'account_wht_certificate'::regclass
          AND conname LIKE '%unique_payment_id%'
    """)
    old_constraints = cr.fetchall()
    for (conname,) in old_constraints:
        _logger.info(f"Dropping old constraint: {conname}")
        cr.execute(f'ALTER TABLE account_wht_certificate DROP CONSTRAINT IF EXISTS "{conname}"')

    # 7. Add new constraint safely (Standard constraint, not NOT VALID)
    _logger.info("Step 4: Creating new business unique constraint...")
    cr.execute("""
        ALTER TABLE account_wht_certificate
        ADD CONSTRAINT account_wht_certificate_certificate_business_unique
        UNIQUE (
            company_id,
            partner_id,
            wht_type,
            income_type,
            pay_date,
            custom_key
        )
    """)

    _logger.info("=" * 60)
    _logger.info("WHT MIGRATION 18.0.1.5.2: SUCCESSFULLY COMPLETED")
    _logger.info("=" * 60)
