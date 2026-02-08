"""JSON file storage handler for athlete data."""

import json
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data.json"


def load_data() -> dict:
    """Load data from the JSON file."""
    default = {"athletes": [], "current_streak": 0, "best_streak": 0}

    if not DATA_FILE.exists():
        return default

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure streak fields exist
            data.setdefault("current_streak", 0)
            data.setdefault("best_streak", 0)
            return data
    except (json.JSONDecodeError, IOError):
        return default


def save_data(data: dict) -> None:
    """Save data to the JSON file."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def athlete_exists(name: str) -> bool:
    """Check if an athlete already exists (case-insensitive)."""
    athletes = get_athletes()
    name_lower = name.lower().strip()
    return any(a["name"].lower().strip() == name_lower for a in athletes)


def add_athlete(name: str, sport: str, country: str | None = None, matched_name: str | None = None) -> bool:
    """Add a new athlete to the data store. Returns False if already exists."""
    if athlete_exists(name):
        return False

    data = load_data()

    athlete = {
        "name": name,
        "sport": sport,
        "country": country,
        "matched_name": matched_name or name,
        "added_at": datetime.now().isoformat()
    }

    data["athletes"].append(athlete)
    save_data(data)
    return True


def get_athletes() -> list[dict]:
    """Get all athletes from the data store."""
    data = load_data()
    return data.get("athletes", [])


def get_stats() -> dict[str, int]:
    """Get count of athletes per sport."""
    athletes = get_athletes()
    stats = {}

    for athlete in athletes:
        sport = athlete.get("sport", "Unknown")
        stats[sport] = stats.get(sport, 0) + 1

    return stats


def get_country_stats() -> dict[str, int]:
    """Get count of athletes per country."""
    athletes = get_athletes()
    stats = {}

    for athlete in athletes:
        country = athlete.get("country") or "Unknown"
        stats[country] = stats.get(country, 0) + 1

    return stats


def clear_data() -> None:
    """Clear all athlete data."""
    save_data({"athletes": [], "current_streak": 0, "best_streak": 0})


def get_streak() -> tuple[int, int]:
    """Get current streak and best streak."""
    data = load_data()
    return data.get("current_streak", 0), data.get("best_streak", 0)


def increment_streak() -> tuple[int, int, bool]:
    """Increment streak on successful add. Returns (current, best, is_new_record)."""
    data = load_data()
    data["current_streak"] = data.get("current_streak", 0) + 1
    current = data["current_streak"]
    best = data.get("best_streak", 0)

    is_new_record = current > best
    if is_new_record:
        data["best_streak"] = current
        best = current

    save_data(data)
    return current, best, is_new_record


def reset_streak() -> None:
    """Reset current streak to 0 (on failed lookup)."""
    data = load_data()
    data["current_streak"] = 0
    save_data(data)
