\
set ON_ERROR_STOP on --   auth_db_user, auth_db_password,
    --   radio_db_user, radio_db_password,
    --   curio_db_user, curio_db_password,
    --   seeksage_db_user, seeksage_db_password,
    --   notestack_db_user, notestack_db_password
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'auth_db_user',
        :'auth_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'auth_db_user'
    ) \ gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'radio_db_user',
        :'radio_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'radio_db_user'
    ) \ gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'curio_db_user',
        :'curio_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'curio_db_user'
    ) \ gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'seeksage_db_user',
        :'seeksage_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'seeksage_db_user'
    ) \ gexec
SELECT format(
        'CREATE ROLE %I LOGIN PASSWORD %L',
        :'notestack_db_user',
        :'notestack_db_password'
    )
WHERE NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'notestack_db_user'
    ) \ gexec -- Always keep role passwords aligned with deployment configuration.
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'auth_db_user',
        :'auth_db_password'
    ) \ gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'radio_db_user',
        :'radio_db_password'
    ) \ gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'curio_db_user',
        :'curio_db_password'
    ) \ gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'seeksage_db_user',
        :'seeksage_db_password'
    ) \ gexec
SELECT format(
        'ALTER ROLE %I WITH LOGIN PASSWORD %L',
        :'notestack_db_user',
        :'notestack_db_password'
    ) \ gexec