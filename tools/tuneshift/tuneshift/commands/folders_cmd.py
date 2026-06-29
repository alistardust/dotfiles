"""Tidal folder management and collection tagging commands."""

from __future__ import annotations

import sys

from tuneshift.db import Database


def handle_tag(args, db: Database) -> int:
    """Tag a playlist with a collection."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1
    db.tag_playlist(playlist.id, args.collection)
    print(f'Tagged "{playlist.name}" with "{args.collection}"')
    return 0


def handle_untag(args, db: Database) -> int:
    """Remove a collection tag from a playlist."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1
    if db.untag_playlist(playlist.id, args.collection):
        print(f'Removed "{args.collection}" from "{playlist.name}"')
    else:
        print(f'"{playlist.name}" is not tagged with "{args.collection}"', file=sys.stderr)
        return 1
    return 0


def handle_collections(args, db: Database) -> int:
    """List collections or show playlists in a collection."""
    if getattr(args, "create_name", None):
        db.create_collection(args.create_name)
        print(f'Created collection "{args.create_name}"')
        return 0

    if getattr(args, "delete_name", None):
        if db.delete_collection(args.delete_name):
            print(f'Deleted collection "{args.delete_name}"')
        else:
            print(f'Collection not found: "{args.delete_name}"', file=sys.stderr)
            return 1
        return 0

    collection_name = getattr(args, "collection", None)
    if collection_name:
        playlists = db.get_collection_playlists(collection_name)
        if not playlists:
            print(f'No playlists in "{collection_name}" (or collection does not exist)')
            return 0
        print(f'Collection "{collection_name}" ({len(playlists)} playlists):')
        for p in playlists:
            print(f"  - {p.name}")
        return 0

    # List all collections
    collections = db.list_collections_with_counts()
    if not collections:
        print("No collections. Create one with: tuneshift collections create <name>")
        return 0
    print("Collections:")
    for name, count in collections:
        print(f"  {name} ({count} playlists)")
    return 0


def handle_folders(args, db: Database) -> int:
    """Manage Tidal folders."""
    from tuneshift.commands.ingest_cmd import _load_client

    action = getattr(args, "action", None)

    if action == "list":
        return _folders_list(db)
    elif action == "import":
        return _folders_import(db)
    elif action == "create":
        return _folders_create(db, args.name)
    elif action == "rename":
        return _folders_rename(db, args.old_name, args.new_name)
    elif action == "delete":
        return _folders_delete(db, args.name)
    elif action == "move":
        return _folders_move(db, args.playlist, args.to)
    elif action == "unassign":
        return _folders_unassign(db, args.playlist)
    elif action == "sync":
        return _folders_sync(db)
    elif action == "pull":
        return _folders_pull(db)
    elif action == "status":
        return _folders_status(db)
    else:
        print("Usage: tuneshift folders <list|import|create|rename|delete|move|unassign|sync|pull|status>",
              file=sys.stderr)
        return 1


def _get_tidal_client():
    """Load and authenticate Tidal client."""
    from tuneshift.commands.ingest_cmd import _load_client
    client = _load_client("tidal")
    if not client or not client.load_session():
        print("Not logged in to Tidal. Run: tuneshift login tidal", file=sys.stderr)
        return None
    return client


def _folders_list(db: Database) -> int:
    """List Tidal folders and their contents."""
    client = _get_tidal_client()
    if not client:
        return 1

    root = client._session.user.folder()
    items = root.items()

    print("Tidal folders:")
    for item in items:
        if hasattr(item, "name") and hasattr(item, "items"):
            # It's a folder
            folder_items = item.items()
            print(f"\n  [{item.name}] ({item.total_number_of_items} items)")
            db.cache_tidal_folder(item.trn, item.name, None)
            for sub in folder_items:
                if hasattr(sub, "name"):
                    print(f"    - {sub.name}")
        elif hasattr(item, "name"):
            # Playlist in root
            print(f"  (root) {item.name}")

    return 0


def _folders_import(db: Database) -> int:
    """Import existing Tidal folder structure."""
    client = _get_tidal_client()
    if not client:
        return 1

    root = client._session.user.folder()
    items = root.items()

    imported_folders = 0
    assigned_playlists = 0

    for item in items:
        if not (hasattr(item, "trn") and hasattr(item, "items")):
            continue

        folder_name = item.name
        folder_id = item.trn
        db.cache_tidal_folder(folder_id, folder_name, None)
        imported_folders += 1
        print(f"  Folder: {folder_name} ({folder_id})")

        folder_items = item.items()
        for sub in folder_items:
            if not hasattr(sub, "name"):
                continue
            # Try to match to local playlist
            local = db.find_playlist_by_name(sub.name)
            if local:
                db.set_playlist_tidal_folder(local.id, folder_id)
                assigned_playlists += 1
                print(f"    -> {sub.name} (linked)")
            else:
                print(f"    -> {sub.name} (no local match)")

    print(f"\nImported {imported_folders} folders, linked {assigned_playlists} playlists")

    # Offer to create collections
    create = input("Create local collections matching folder names? [y/N] ").strip().lower()
    if create in ("y", "yes"):
        for folder in db.get_cached_tidal_folders():
            col_id = db.create_collection(folder["name"])
            # Tag playlists in this folder with the collection
            for p in db.get_playlists_by_tidal_folder(folder["tidal_id"]):
                db.tag_playlist(p.id, folder["name"])
        print("Collections created and playlists tagged.")

    return 0


def _folders_create(db: Database, name: str) -> int:
    """Create a folder on Tidal."""
    client = _get_tidal_client()
    if not client:
        return 1

    root = client._session.user.folder()
    # tidalapi creates folders by adding items; we need to use the API directly
    # The folder API requires creating via the session
    try:
        import requests
        session = client._session
        resp = requests.put(
            f"https://api.tidal.com/v2/my-collection/playlists/folders/create-folder",
            headers={"Authorization": f"Bearer {session.access_token}"},
            params={"folderId": "root", "name": name, "countryCode": session.country_code},
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            folder_id = data.get("data", {}).get("trn", "")
            if folder_id:
                db.cache_tidal_folder(folder_id, name)
                print(f'Created folder "{name}" on Tidal (id: {folder_id})')
                return 0
        # Fallback: try via tidalapi if available
        print(f"Failed to create folder: {resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"Failed to create folder: {exc}", file=sys.stderr)
        return 1


def _folders_rename(db: Database, old_name: str, new_name: str) -> int:
    """Rename a folder on Tidal."""
    folder = db.get_tidal_folder_by_name(old_name)
    if not folder:
        print(f'Folder not found in cache: "{old_name}". Run: tuneshift folders list', file=sys.stderr)
        return 1

    client = _get_tidal_client()
    if not client:
        return 1

    try:
        tidal_folder = client._session.folder(folder["tidal_id"])
        tidal_folder.rename(new_name)
        db.cache_tidal_folder(folder["tidal_id"], new_name, folder.get("parent_tidal_id"))
        print(f'Renamed "{old_name}" to "{new_name}" on Tidal')
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Failed to rename: {exc}", file=sys.stderr)
        return 1


def _folders_delete(db: Database, name: str) -> int:
    """Delete a folder on Tidal."""
    folder = db.get_tidal_folder_by_name(name)
    if not folder:
        print(f'Folder not found in cache: "{name}". Run: tuneshift folders list', file=sys.stderr)
        return 1

    # Show affected playlists
    affected = db.get_playlists_by_tidal_folder(folder["tidal_id"])
    if affected:
        print(f'Deleting "{name}" will unassign {len(affected)} playlists:')
        for p in affected:
            print(f"  - {p.name}")

    confirm = input(f'Delete folder "{name}" on Tidal? [y/N] ').strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return 0

    client = _get_tidal_client()
    if not client:
        return 1

    try:
        tidal_folder = client._session.folder(folder["tidal_id"])
        tidal_folder.remove()
        count = db.clear_tidal_folder_assignments(folder["tidal_id"])
        db.remove_tidal_folder_cache(folder["tidal_id"])
        print(f'Deleted "{name}" on Tidal. {count} playlists moved to root.')
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Failed to delete: {exc}", file=sys.stderr)
        return 1


def _folders_move(db: Database, playlist_name: str, folder_name: str) -> int:
    """Assign a playlist to a Tidal folder."""
    playlist = db.find_playlist_by_name(playlist_name)
    if not playlist:
        print(f"Playlist not found: {playlist_name}", file=sys.stderr)
        return 1

    folder = db.get_tidal_folder_by_name(folder_name)
    if not folder:
        print(f'Folder not found in cache: "{folder_name}". Run: tuneshift folders list', file=sys.stderr)
        return 1

    db.set_playlist_tidal_folder(playlist.id, folder["tidal_id"])
    print(f'Assigned "{playlist.name}" to folder "{folder_name}". Run: tuneshift folders sync')
    return 0


def _folders_unassign(db: Database, playlist_name: str) -> int:
    """Remove folder assignment from a playlist."""
    playlist = db.find_playlist_by_name(playlist_name)
    if not playlist:
        print(f"Playlist not found: {playlist_name}", file=sys.stderr)
        return 1

    db.set_playlist_tidal_folder(playlist.id, None)
    print(f'Unassigned "{playlist.name}" from folder. Will move to root on next sync.')
    return 0


def _folders_sync(db: Database) -> int:
    """Push all folder assignments to Tidal."""
    client = _get_tidal_client()
    if not client:
        return 1

    # Refresh folder cache
    root = client._session.user.folder()
    for item in root.items():
        if hasattr(item, "trn") and hasattr(item, "items"):
            db.cache_tidal_folder(item.trn, item.name, None)

    # Get all playlists with folder assignments
    all_playlists = db.list_playlists()
    moved = 0
    errors = 0

    for playlist in all_playlists:
        if not playlist.tidal_folder_id:
            continue

        # Get platform playlist ID
        platform_id = db.get_platform_playlist_id(playlist.id, "tidal")
        if not platform_id:
            continue

        try:
            # Get the target folder
            target_folder = client._session.folder(playlist.tidal_folder_id)
            # Build the TRN for the playlist
            playlist_trn = f"trn:playlist:{platform_id}"
            target_folder.add_items([playlist_trn])
            moved += 1
            folder_info = next(
                (f for f in db.get_cached_tidal_folders() if f["tidal_id"] == playlist.tidal_folder_id),
                None,
            )
            folder_name = folder_info["name"] if folder_info else playlist.tidal_folder_id
            print(f"  {playlist.name} -> {folder_name}")
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"  {playlist.name}: failed ({exc})", file=sys.stderr)
            errors += 1

    print(f"\nSynced: {moved} moved, {errors} errors")
    return 0


def _folders_pull(db: Database) -> int:
    """Update local folder assignments from Tidal state."""
    client = _get_tidal_client()
    if not client:
        return 1

    root = client._session.user.folder()
    items = root.items()
    updated = 0

    # Clear all local assignments first
    db.conn.execute("UPDATE playlists SET tidal_folder_id = NULL")

    for item in items:
        if not (hasattr(item, "trn") and hasattr(item, "items")):
            continue

        folder_id = item.trn
        db.cache_tidal_folder(folder_id, item.name, None)

        for sub in item.items():
            if hasattr(sub, "name"):
                local = db.find_playlist_by_name(sub.name)
                if local:
                    db.set_playlist_tidal_folder(local.id, folder_id)
                    updated += 1

    db.conn.commit()
    print(f"Pulled Tidal folder state: {updated} playlists updated")
    return 0


def _folders_status(db: Database) -> int:
    """Show local vs Tidal folder state."""
    all_playlists = db.list_playlists()
    assigned = [(p, p.tidal_folder_id) for p in all_playlists if p.tidal_folder_id]
    unassigned = [p for p in all_playlists if not p.tidal_folder_id]

    folders = db.get_cached_tidal_folders()

    print("Folder assignments:")
    for folder in folders:
        playlists = db.get_playlists_by_tidal_folder(folder["tidal_id"])
        print(f"\n  [{folder['name']}] ({len(playlists)} playlists)")
        for p in playlists:
            print(f"    - {p.name}")

    if unassigned:
        print(f"\n  (root) ({len(unassigned)} playlists)")
        for p in unassigned[:10]:
            print(f"    - {p.name}")
        if len(unassigned) > 10:
            print(f"    ... +{len(unassigned) - 10} more")

    return 0
