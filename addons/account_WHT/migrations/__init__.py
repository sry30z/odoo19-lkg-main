# -*- coding: utf-8 -*-
"""
WHT Certificate Migration Package

Contains migration scripts for schema changes and data updates.
Migrations follow semantic versioning: major.minor.patch.description

Version 15.0.0.1: Upgrade uniqueness constraints
- Replace naive UNIQUE(payment_id) with business-safe composite uniqueness
- Add production-safe composite constraints
- Update custom_key generation logic
