\set ON_ERROR_STOP on

-- Required psql variables:
--   auth_db_name, auth_db_user, radio_db_name, radio_db_user

SELECT format(
  'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
  :'auth_db_name',
  :'auth_db_user'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'auth_db_name'
)\gexec

SELECT format(
  'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
  :'radio_db_name',
  :'radio_db_user'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'radio_db_name'
)\gexec

SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'auth_db_name', :'auth_db_user')\gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'radio_db_name', :'radio_db_user')\gexec
