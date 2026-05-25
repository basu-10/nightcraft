\set ON_ERROR_STOP on
    --   auth_db_user, auth_db_password, radio_db_user, radio_db_password
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