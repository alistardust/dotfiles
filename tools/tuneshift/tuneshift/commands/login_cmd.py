"""Login command: authenticate with a streaming platform."""
import sys


def handle_login(args, db) -> int:
    """Authenticate with a streaming platform."""
    from tuneshift.commands.ingest_cmd import _load_client

    client = _load_client(args.platform)
    if client is None:
        print(f"Unknown platform: {args.platform}", file=sys.stderr)
        return 1

    print(f"Logging in to {args.platform}...")
    if client.login():
        print(f"Authenticated with {args.platform}.")
        return 0
    else:
        print(f"Authentication failed for {args.platform}.", file=sys.stderr)
        return 1
