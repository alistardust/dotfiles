"""Preferences command: manage global version preferences."""
import copy
import json
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11

DEFAULT_PREFS = {
    "version_preferences": {
        "prefer": ["studio", "original", "explicit"],
        "avoid": ["live", "remix", "acoustic", "radio-edit", "clean"],
        "duration_tolerance_percent": 15.0,
    }
}

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tuneshift" / "preferences.toml"


def load_global_preferences(config_path: Path | None = None) -> dict:
    """Load global preferences from TOML config file."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return copy.deepcopy(DEFAULT_PREFS)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Merge with defaults (deep copy to avoid mutating module-level constant)
    result = copy.deepcopy(DEFAULT_PREFS)
    if "version_preferences" in data:
        result["version_preferences"].update(data["version_preferences"])
    return result


def _write_toml(path: Path, data: dict) -> None:
    """Write dict as TOML (simple implementation for flat preferences)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, val in values.items():
            if isinstance(val, list):
                items = ", ".join(f'"{v}"' for v in val)
                lines.append(f"{key} = [{items}]")
            elif isinstance(val, (int, float)):
                lines.append(f"{key} = {val}")
            else:
                lines.append(f'{key} = "{val}"')
        lines.append("")
    path.write_text("\n".join(lines))


def handle_prefs(args) -> int:
    """Show or set global preferences."""
    config_path = Path(getattr(args, "config_path", None) or DEFAULT_CONFIG_PATH)

    if args.action == "show":
        prefs = load_global_preferences(config_path)
        print("Global preferences:")
        for section, values in prefs.items():
            print(f"\n  [{section}]")
            for key, val in values.items():
                print(f"    {key} = {val}")
        return 0

    if args.action == "set":
        prefs = load_global_preferences(config_path)
        # Parse dotted key like "version_preferences.prefer"
        parts = args.key.split(".", 1)
        if len(parts) != 2:
            print(f"Key must be section.key format: {args.key}")
            return 1
        section, key = parts
        if section not in prefs:
            prefs[section] = {}
        # Try to parse value as JSON
        try:
            prefs[section][key] = json.loads(args.value)
        except (json.JSONDecodeError, TypeError):
            prefs[section][key] = args.value
        _write_toml(config_path, prefs)
        print(f"Set {args.key} = {prefs[section][key]}")
        return 0

    print(f"Unknown action: {args.action}")
    return 1
