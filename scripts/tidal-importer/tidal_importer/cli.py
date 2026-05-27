"""CLI entrypoint for tidal-importer."""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tidal-importer",
        description="Import CSV playlists into Tidal",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rec = subparsers.add_parser(
        "reconcile",
        help="Search Tidal for tracks in a CSV and produce reconciliation JSON",
    )
    rec.add_argument("input", help="CSV file or directory of CSVs")
    rec.add_argument("-o", "--output", help="Output directory for reconciliation JSON")
    rec.add_argument("--auto", action="store_true", help="Auto-resolve ambiguous matches")

    imp = subparsers.add_parser(
        "import",
        help="Create Tidal playlists from reconciliation JSON",
    )
    imp.add_argument("input", help="Reconciliation JSON file or directory")
    imp.add_argument("--name", help="Override playlist name")
    imp.add_argument("--append", action="store_true", help="Append to existing playlist")
    imp.add_argument("--force", action="store_true", help="Create even if name exists")
    imp.add_argument("--dry-run", action="store_true", help="Show plan without creating")

    args = parser.parse_args()

    if args.command == "reconcile":
        from tidal_importer.reconcile import run_reconcile
        run_reconcile(args)
    elif args.command == "import":
        from tidal_importer.importer import run_import
        run_import(args)


if __name__ == "__main__":
    main()
