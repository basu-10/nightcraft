\set ON_ERROR_STOP on

-- Required psql variables:
--   auth_db_user, auth_db_password,
--   radio_db_user, radio_db_password,
--   neera_db_user, neera_db_password,
--   notestack_db_user, notestack_db_password,
--   green_pledge_db_user, green_pledge_db_password,
--   alfred_db_user, alfred_db_password
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'auth_db_user',
        :'auth_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'auth_db_user'
    ) \gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'radio_db_user',
        :'radio_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'radio_db_user'
    ) \gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'neera_db_user',
        :'neera_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'neera_db_user'
    ) \gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'notestack_db_user',
        :'notestack_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'notestack_db_user'
    ) \gexec -- Always keep role passwords aligned with deployment configuration.
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'auth_db_user',
        :'auth_db_password'
    ) \gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'radio_db_user',
        :'radio_db_password'
    ) \gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'neera_db_user',
        :'neera_db_password'
    ) \gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'notestack_db_user',
        :'notestack_db_password'
    ) \gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'alfred_db_user',
        :'alfred_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'alfred_db_user'
    ) \gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'alfred_db_user',
        :'alfred_db_password'
    ) \gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'green_pledge_db_user',
        :'green_pledge_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'green_pledge_db_user'
    ) \gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'green_pledge_db_user',
        :'green_pledge_db_password'
    ) \gexec