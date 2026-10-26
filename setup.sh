#!/usr/bin/env bash
# Creates the lab_qc database, the tables, and loads the CSV data.
# Usage: ./setup.sh            (uses your default PostgreSQL user)
set -euo pipefail

DB_NAME="${DB_NAME:-lab_qc}"

createdb "$DB_NAME" 2>/dev/null || echo "Database $DB_NAME already exists, reusing it."
psql -v ON_ERROR_STOP=1 -d "$DB_NAME" -f schema.sql
psql -v ON_ERROR_STOP=1 -d "$DB_NAME" -f load_data.sql

echo
echo "Done. Quick check:"
psql -d "$DB_NAME" -c "SELECT * FROM v_test_summary ORDER BY test_code;"
