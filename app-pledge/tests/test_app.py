from importlib import import_module


def test_package_imports():
    # Importing the package must not require a live database. create_app is only
    # invoked at runtime (and needs PostgreSQL), so we assert the factory and
    # key submodules import cleanly.
    pkg = import_module("greenpledge")
    assert callable(pkg.create_app)

    import_module("greenpledge.models")
    import_module("greenpledge.auth.current_user")
    import_module("greenpledge.landing")
    import_module("greenpledge.cli")
    import_module("greenpledge.guards")
    import_module("greenpledge.utils")
