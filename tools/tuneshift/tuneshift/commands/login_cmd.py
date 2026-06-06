"""Login command: authenticate with a streaming platform."""
import sys


def handle_login(args, db) -> int:
    """Authenticate with a streaming platform."""
    from tuneshift.commands.ingest_cmd import _load_client

    client = _load_client(args.platform)
    if client is None:
        print(f"Unknown platform: {args.platform}", file=sys.stderr)
        return 1

    # Check if already logged in
    if client.load_session():
        print(f"Already authenticated with {args.platform}.")
        return 0

    print(f"Logging in to {args.platform}...")

    # Tidal uses a two-step flow: login() returns URL, login_wait() polls
    # YT Music uses a single-step flow: login() runs interactively and returns bool
    if hasattr(client, "login_wait"):
        url = client.login()
        print(f"\nOpen this URL to authenticate:\n  {url}\n")
        print("Waiting for authorization...")
        if client.login_wait(timeout=300.0):
            print(f"Authenticated with {args.platform}.")
            return 0
        else:
            print(f"Authentication timed out for {args.platform}.", file=sys.stderr)
            return 1
    else:
        result = client.login()
        if result:
            print(f"Authenticated with {args.platform}.")
            return 0
        else:
            print(f"Authentication failed for {args.platform}.", file=sys.stderr)
            return 1
