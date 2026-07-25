\set ON_ERROR_STOP on

-- Required psql variables:
--   auth_db_name, auth_db_user,
--   radio_db_name, radio_db_user,
--   neera_db_name, neera_db_user,
--   notestack_db_name, notestack_db_user,
--   green_pledge_db_name, green_pledge_db_user,
--   alfred_db_name, alfred_db_user,
--   quickposts_db_name, quickposts_db_user,
--   noteflow_db_name, noteflow_db_user,
--   scratchpad_db_name, scratchpad_db_user,
--   telemetry_db_name, telemetry_db_user
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'telemetry_db_name',
        :'telemetry_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'telemetry_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'telemetry_db_name',
        :'telemetry_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'auth_db_name',
        :'auth_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'auth_db_name'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'radio_db_name',
        :'radio_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'radio_db_name'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'neera_db_name',
        :'neera_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'neera_db_name'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'notestack_db_name',
        :'notestack_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'notestack_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'auth_db_name',
        :'auth_db_user'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'radio_db_name',
        :'radio_db_user'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'neera_db_name',
        :'neera_db_user'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'notestack_db_name',
        :'notestack_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'alfred_db_name',
        :'alfred_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'alfred_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'alfred_db_name',
        :'alfred_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'green_pledge_db_name',
        :'green_pledge_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'green_pledge_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'green_pledge_db_name',
        :'green_pledge_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'quickposts_db_name',
        :'quickposts_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'quickposts_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'quickposts_db_name',
        :'quickposts_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'noteflow_db_name',
        :'noteflow_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'noteflow_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'noteflow_db_name',
        :'noteflow_db_user'
    ) \gexec
SELECT format(
        'CREATE DATABASE %I OWNER %I ENCODING ''UTF8''',
        :'scratchpad_db_name',
        :'scratchpad_db_user'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_database
        WHERE datname = :'scratchpad_db_name'
    ) \gexec
SELECT format(
        'GRANT ALL PRIVILEGES ON DATABASE %I TO %I',
        :'scratchpad_db_name',
        :'scratchpad_db_user'
    ) \gexec