#!/usr/bin/env python3
"""Minimal manifest reader for the Nightcraft product registry.

Dependency-light: standard library + PyYAML (already present on the target).
Used both as an importable module (by the runtime manager) and as a CLI by
the bash scripts:

    python3 products.py get <slug> <dotted.field>   e.g.  get green runtime.policy
    python3 products.py slugs [--policy on_demand]    list product slugs
    python3 products.py public_paths <slug>           list public paths (space separated)

Manifest resolution order:
    1. --manifest PATH
    2. NC_PRODUCTS_YML env var
    3. /etc/nightcraft/products.yml  (deployed target location)
    4. ../products.yml relative to this script (repo checkout)
"""

import argparse
import os
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required (apt-get install python3-yaml)\n")
    sys.exit(1)


def resolve_manifest(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("NC_PRODUCTS_YML")
    if env:
        return env
    if os.path.exists("/etc/nightcraft/products.yml"):
        return "/etc/nightcraft/products.yml"
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.join(here, "..", "products.yml")
    if os.path.exists(repo):
        return repo
    return "/etc/nightcraft/products.yml"


def load_manifest(path):
    if not os.path.exists(path):
        sys.stderr.write("Manifest not found: %s\n" % path)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    products = data.get("products", {}) or {}
    return products


def get_field(products, slug, field):
    product = products.get(slug)
    if product is None:
        sys.stderr.write("Unknown product slug: %s\n" % slug)
        sys.exit(1)
    node = product
    for part in field.split("."):
        if not isinstance(node, dict) or part not in node:
            sys.stderr.write("Field not found: %s.%s\n" % (slug, field))
            sys.exit(1)
        node = node[part]
    if isinstance(node, (list, dict)):
        return yaml.safe_dump(node, default_flow_style=True).strip()
    return str(node)


def list_slugs(products, policy=None):
    slugs = []
    for slug, product in products.items():
        prod_policy = (product.get("runtime") or {}).get("policy")
        if policy is None or prod_policy == policy:
            slugs.append(slug)
    return slugs


def public_paths(products, slug):
    product = products.get(slug)
    if product is None:
        sys.stderr.write("Unknown product slug: %s\n" % slug)
        sys.exit(1)
    return product.get("public_paths") or []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nightcraft product manifest reader")
    parser.add_argument("--manifest", help="path to products.yml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="print a dotted field for a slug")
    p_get.add_argument("slug")
    p_get.add_argument("field")

    p_slugs = sub.add_parser("slugs", help="list product slugs")
    p_slugs.add_argument("--policy", help="filter by runtime.policy")

    p_paths = sub.add_parser("public_paths", help="list public_paths for a slug")
    p_paths.add_argument("slug")

    args = parser.parse_args(argv)
    manifest = resolve_manifest(args.manifest)
    products = load_manifest(manifest)

    if args.cmd == "get":
        print(get_field(products, args.slug, args.field))
    elif args.cmd == "slugs":
        for slug in list_slugs(products, args.policy):
            print(slug)
    elif args.cmd == "public_paths":
        for path in public_paths(products, args.slug):
            print(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
