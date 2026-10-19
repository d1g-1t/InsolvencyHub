#!/bin/bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	SELECT 'CREATE DATABASE insolvency_hub_test'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'insolvency_hub_test')\gexec
EOSQL
