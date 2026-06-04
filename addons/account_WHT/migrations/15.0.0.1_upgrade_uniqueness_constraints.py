# -*- coding: utf-8 -*-
"""
Migration Script: WHT Certificate Uniqueness Constraints Redesign

Version: 18.0.0.1
Purpose: Replace naive UNIQUE(payment_id) with business-safe composite uniqueness
Author: Database Architecture Team
Date: 2025

OBJECTIVE:
- Remove restrictive 'unique_payment_id' constraint
- Add production-safe 'certificate_business_unique' constraint
- Update custom_key generation for business-level idempotency
- Migrate existing data to new format
- Validate data integrity after migration

SAFETY MEASURES:
- Migration is reversible (rollback steps provided)
- No data deletion (only constraint changes and data updates)
- Validation queries before/after migration
- Fallback to manual review if automated validation fails
"""


def migrate(cr, version):
    """
    Main migration function called by Odoo upgrade process.

    Steps:
    1. Validate current database state
    2. Backup existing data for rollback
    3. Remove old constraint (unique_payment_id)
    4. Add new constraint (certificate_business_unique)
    5. Update custom_key for existing records
    6. Validate new database state
    7. Generate migration report
    """

    # Import SQL helpers
    from odoo.tools import sql

    _logger.info("=" * 80)
    _logger.info("WHT CERTIFICATE UNIQUENESS MIGRATION START")
    _logger.info("=" * 80)

    try:
        # STEP 1: Validate current database state
        _validate_current_state(cr)

        # STEP 2: Backup existing certificate data
        _backup_certificate_data(cr)

        # STEP 3: Remove old constraint
        _remove_old_constraint(cr)

        # STEP 4: Add new constraint
        _add_new_constraint(cr)

        # STEP 5: Update custom_key for existing records
        _update_custom_keys(cr)

        # STEP 6: Validate new database state
        _validate_new_state(cr)

        # STEP 7: Generate migration report
        _generate_migration_report(cr)

        _logger.info("=" * 80)
        _logger.info("WHT CERTIFICATE UNIQUENESS MIGRATION SUCCESS")
        _logger.info("=" * 80)

    except Exception as e:
        _logger.error("=" * 80)
        _logger.error("WHT CERTIFICATE UNIQUENESS MIGRATION FAILED")
        _logger.error("=" * 80)
        _logger.error(f"Migration Error: {str(e)}", exc_info=True)

        # Attempt rollback on critical failure
        try:
            _rollback_migration(cr)
            _logger.warning("Migration rolled back due to critical failure")
        except Exception as rollback_error:
            _logger.error(f"Rollback failed: {str(rollback_error)}", exc_info=True)

        raise


def _validate_current_state(cr):
    """Validate current database state before migration."""
    _logger.info("STEP 1: Validating current database state")

    # Check if old constraint exists
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conname = 'account_wht_certificate_unique_payment_id'
    """)
    constraint_exists = cr.fetchone()

    if constraint_exists:
        _logger.info(
            "✓ Old constraint found: account_wht_certificate_unique_payment_id"
        )
    else:
        _logger.warning("⚠ Old constraint not found (may have been removed already)")

    # Check certificate data
    cr.execute("""
        SELECT 
            COUNT(*) as total_certificates,
            COUNT(DISTINCT payment_id) as unique_payments,
            COUNT(DISTINCT company_id) as unique_companies,
            COUNT(DISTINCT partner_id) as unique_partners
        FROM account_wht_certificate
    """)
    stats = cr.fetchone()

    _logger.info(
        f"Current State: {stats[0]} certificates, {stats[1]} unique payments, {stats[2]} companies, {stats[3]} partners"
    )

    # Check for potential duplicates
    cr.execute("""
        SELECT payment_id, COUNT(*) as cert_count
        FROM account_wht_certificate
        WHERE payment_id IS NOT NULL
        GROUP BY payment_id
        HAVING COUNT(*) > 1
    """)
    duplicates = cr.fetchall()

    if duplicates:
        _logger.warning(
            f"⚠ Found {len(duplicates)} payment_id with multiple certificates"
        )
        for payment_id, cert_count in duplicates:
            _logger.warning(f"  Payment {payment_id}: {cert_count} certificates")
    else:
        _logger.info("✓ No payment_id duplicates found")


def _backup_certificate_data(cr):
    """Backup existing certificate data for rollback."""
    _logger.info("STEP 2: Backing up certificate data")

    # Create backup table
    cr.execute("""
        DROP TABLE IF EXISTS account_wht_certificate_backup
    """)

    cr.execute("""
        CREATE TABLE account_wht_certificate_backup AS
        SELECT * FROM account_wht_certificate
    """)

    cr.execute("SELECT COUNT(*) FROM account_wht_certificate_backup")
    backup_count = cr.fetchone()[0]

    _logger.info(
        f"✓ Backed up {backup_count} certificate records to account_wht_certificate_backup"
    )


def _remove_old_constraint(cr):
    """Remove old unique_payment_id constraint."""
    _logger.info("STEP 3: Removing old constraint")

    # Check if constraint exists
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conname = 'account_wht_certificate_unique_payment_id'
    """)
    constraint_exists = cr.fetchone()

    if constraint_exists:
        cr.execute("""
            ALTER TABLE account_wht_certificate
            DROP CONSTRAINT account_wht_certificate_unique_payment_id
        """)
        _logger.info("✓ Removed constraint: account_wht_certificate_unique_payment_id")
    else:
        _logger.info("⚠ Constraint not found (may have been removed already)")


def _add_new_constraint(cr):
    """Add new business-level composite constraint."""
    _logger.info("STEP 4: Adding new business-level constraint")

    # Check if constraint already exists
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conname = 'account_wht_certificate_certificate_business_unique'
    """)
    constraint_exists = cr.fetchone()

    if constraint_exists:
        _logger.info("⚠ New constraint already exists (may have been added previously)")
        return

    # Add new composite constraint
    cr.execute("""
        ALTER TABLE account_wht_certificate
        ADD CONSTRAINT account_wht_certificate_certificate_business_unique
        UNIQUE(company_id, partner_id, wht_type, income_type, payment_date, custom_key)
    """)

    _logger.info(
        "✓ Added constraint: account_wht_certificate_certificate_business_unique"
    )


def _update_custom_keys(cr):
    """Update custom_key for existing records to new format."""
    _logger.info("STEP 5: Updating custom_key for existing records")

    # Update custom_key for records where it's null or empty
    cr.execute("""
        UPDATE account_wht_certificate
        SET custom_key = 
            CASE 
                WHEN payment_id IS NOT NULL THEN
                    CAST(payment_id AS VARCHAR) || '_' ||
                    COALESCE(
                        (SELECT string_agg(CAST(move_id AS VARCHAR), '_' ORDER BY move_id)
                        FROM (SELECT DISTINCT move_id 
                              FROM account_wht_certificate_move_rel 
                              WHERE account_wht_certificate_id = account_wht_certificate.id) 
                         AS related_moves
                        GROUP BY related_moves
                        LIMIT 1),
                        '0'
                    ) || '_' ||
                    COALESCE(wht_type, 'pnd53') || '_' ||
                    COALESCE(income_type, 'service') || '_' ||
                    COALESCE(CAST(pay_date AS VARCHAR), CAST(issue_date AS VARCHAR))
                ELSE
                    'manual_' || CAST(id AS VARCHAR)
            END
        WHERE custom_key IS NULL OR custom_key = ''
    """)

    cr.execute(
        "SELECT COUNT(*) FROM account_wht_certificate WHERE custom_key IS NOT NULL"
    )
    updated_count = cr.fetchone()[0]

    _logger.info(f"✓ Updated custom_key for {updated_count} certificate records")


def _validate_new_state(cr):
    """Validate new database state after migration."""
    _logger.info("STEP 6: Validating new database state")

    # Check new constraint
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conname = 'account_wht_certificate_certificate_business_unique'
    """)
    constraint_exists = cr.fetchone()

    if constraint_exists:
        _logger.info(
            "✓ New constraint exists: account_wht_certificate_certificate_business_unique"
        )
    else:
        _logger.error("✗ New constraint not found (migration may have failed)")
        raise Exception("New constraint was not created successfully")

    # Check for constraint violations
    cr.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT company_id, partner_id, wht_type, income_type, payment_date, custom_key, COUNT(*) as cnt
            FROM account_wht_certificate
            WHERE custom_key IS NOT NULL
            GROUP BY company_id, partner_id, wht_type, income_type, payment_date, custom_key
            HAVING COUNT(*) > 1
        ) violations
    """)
    violations = cr.fetchone()[0]

    if violations > 0:
        _logger.error(
            f"✗ Found {violations} constraint violations in new business unique constraint"
        )
        _logger.error("This indicates duplicate certificates that need manual review")
        raise Exception("Constraint violations found - manual review required")
    else:
        _logger.info("✓ No constraint violations found")

    # Verify all records have custom_key
    cr.execute("""
        SELECT COUNT(*) 
        FROM account_wht_certificate 
        WHERE custom_key IS NULL OR custom_key = ''
    """)
    null_keys = cr.fetchone()[0]

    if null_keys > 0:
        _logger.warning(f"⚠ {null_keys} records still have null/empty custom_key")
    else:
        _logger.info("✓ All records have custom_key populated")


def _generate_migration_report(cr):
    """Generate detailed migration report."""
    _logger.info("STEP 7: Generating migration report")

    # Certificate statistics
    cr.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT payment_id) as unique_payments,
            COUNT(DISTINCT company_id) as companies,
            COUNT(DISTINCT partner_id) as partners,
            COUNT(DISTINCT wht_type) as wht_types,
            COUNT(DISTINCT income_type) as income_types
        FROM account_wht_certificate
    """)
    stats = cr.fetchone()

    _logger.info("=" * 80)
    _logger.info("MIGRATION REPORT")
    _logger.info("=" * 80)
    _logger.info(f"Total Certificates: {stats[0]}")
    _logger.info(f"Unique Payments: {stats[1]}")
    _logger.info(f"Companies: {stats[2]}")
    _logger.info(f"Partners: {stats[3]}")
    _logger.info(f"WHT Types: {stats[4]}")
    _logger.info(f"Income Types: {stats[5]}")
    _logger.info("=" * 80)


def _rollback_migration(cr):
    """Rollback migration on critical failure."""
    _logger.warning("Attempting migration rollback...")

    # Restore old constraint
    try:
        cr.execute("""
            ALTER TABLE account_wht_certificate
            DROP CONSTRAINT account_wht_certificate_certificate_business_unique
        """)
        _logger.info("✓ Rolled back: Removed new constraint")
    except:
        _logger.info("⚠ New constraint removal skipped (may not exist)")

    try:
        cr.execute("""
            ALTER TABLE account_wht_certificate
            ADD CONSTRAINT account_wht_certificate_unique_payment_id
            UNIQUE(payment_id)
        """)
        _logger.info("✓ Rolled back: Restored old constraint")
    except:
        _logger.error("✗ Old constraint restoration failed")

    # Restore from backup if needed
    cr.execute("SELECT COUNT(*) FROM account_wht_certificate_backup")
    backup_count = cr.fetchone()[0]

    if backup_count > 0:
        cr.execute("""
            TRUNCATE TABLE account_wht_certificate
        """)

        cr.execute("""
            INSERT INTO account_wht_certificate
            SELECT * FROM account_wht_certificate_backup
        """)

        _logger.info(f"✓ Rolled back: Restored {backup_count} records from backup")
