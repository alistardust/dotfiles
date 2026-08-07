#!/usr/bin/env python3
# skills/where-were-we/scripts/wwm.py
"""where-were-we command line entry point.

Subcommands map to the design's data flow stages. The model calls these; it
never formats output or writes the ledger itself.
"""

from __future__ import annotations

import argparse
import json
import sys

import wwm_collect
import wwm_history
import wwm_ledger
import wwm_render
import wwm_session


def _require_runtime() -> None:
    if not wwm_session.is_copilot_runtime():
        raise wwm_session.UnsupportedRuntime(
            "Copilot session store not found. where-were-we supports Copilot "
            "CLI only in v1; it will not read another tool's history."
        )


def _resolve(args) -> str:
    _require_runtime()
    explicit = getattr(args, "session", None)
    session_id = wwm_session.resolve_session_id(explicit)
    if explicit:
        known = wwm_history.session_exists(session_id)
        if not known and not wwm_session.ledger_path(session_id).exists():
            raise wwm_session.SessionUnknown(
                f"Session '{session_id}' is not in the store."
            )
    return session_id


def cmd_collect(args) -> int:
    print(json.dumps(wwm_collect.collect(_resolve(args)), indent=2))
    return 0


def cmd_render(args) -> int:
    """Collect in-process rather than reading a bundle from a file.

    The bundle contains raw session text. Routing it through a temp file put
    that text on disk outside ~/.copilot/session-state, world-readable under
    the default umask, and contradicted this skill's own PHI posture.
    Re-reading the store costs one extra read-only query and leaves nothing
    behind.

    Resolution goes through the same gate as every other subcommand. Calling
    resolve_session_id() directly here skipped both the runtime check and the
    unknown-session refusal, so `render --session ghost` silently produced a
    confident, empty summary for a session that does not exist.
    """
    bundle = wwm_collect.collect(_resolve(args))
    out = wwm_render.render(
        bundle, level=args.level, section=args.section, prose=args.prose
    )
    print(out)
    return 0


def cmd_record(args) -> int:
    wwm_ledger.record(
        _resolve(args),
        kind=args.kind,
        text=args.text,
        why=args.why,
        rejected=args.rejected,
    )
    print(f"recorded {args.kind}")
    return 0


def cmd_adopt(args) -> int:
    target = _resolve(args)
    wwm_ledger.adopt(source=args.source, target=target)
    print(f"adopted ledger from {args.source}")
    return 0


def cmd_sessions(args) -> int:
    """Listing sessions is how a user finds one, so it needs no current session.

    It is still gated on the runtime: on a foreign tool there is nothing to
    list and saying so beats printing an empty table.
    """
    _require_runtime()
    rows = wwm_history.recent_sessions(days=args.days, limit=args.limit)
    total = wwm_history.count_sessions_in_window(days=args.days)
    for row in rows:
        summary = (row["summary"] or "(no summary)")[:40]
        repo = (row["repository"] or "?")[:18]
        updated = (row["updated_at"] or "")[:10]
        print(f"  {summary:<40} {repo:<18} {updated}")
    if total > len(rows):
        print(f"\n  {total - len(rows)} more in the last {args.days} days")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wwm")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_session(p):
        p.add_argument("--session", help="session ID; defaults to the current session")
        return p

    with_session(sub.add_parser("collect")).set_defaults(func=cmd_collect)

    render = with_session(sub.add_parser("render"))
    render.add_argument("--level", default="tldr", choices=wwm_render.LEVELS)
    render.add_argument("--section", default=None)
    render.add_argument("--prose", default="")
    render.set_defaults(func=cmd_render)

    record = with_session(sub.add_parser("record"))
    record.add_argument(
        "--kind",
        required=True,
        choices=["decision", "thread", "blocker", "state", "next", "goal"],
    )
    record.add_argument("--text", required=True)
    record.add_argument("--why", default="")
    record.add_argument("--rejected", default="")
    record.set_defaults(func=cmd_record)

    adopt = with_session(sub.add_parser("adopt"))
    adopt.add_argument("--source", required=True)
    adopt.set_defaults(func=cmd_adopt)

    sessions = sub.add_parser("sessions")
    sessions.add_argument("--days", type=int, default=wwm_history.SESSION_WINDOW_DAYS)
    sessions.add_argument("--limit", type=int, default=wwm_history.SESSION_LIMIT)
    sessions.set_defaults(func=cmd_sessions)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        wwm_session.SessionUnknown,
        wwm_session.UnsupportedRuntime,
        wwm_history.StoreUnavailable,
        wwm_render.UnknownSection,
    ) as err:
        print(f"where-were-we: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
