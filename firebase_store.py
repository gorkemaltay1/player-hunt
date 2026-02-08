"""Firebase Realtime Database storage handler for Player Hunt."""

import requests
import hashlib
import random
import string
from datetime import datetime

FIREBASE_URL = "https://player-hunt-89dc3-default-rtdb.europe-west1.firebasedatabase.app"


def _get_room_url(room_code: str) -> str:
    """Get Firebase URL for a specific room."""
    return f"{FIREBASE_URL}/rooms/{room_code}"


def _hash_password(password: str) -> str:
    """Hash a password for storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_room_code() -> str:
    """Generate a random 6-character room code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(6))


def create_room(room_code: str, password: str, creator: str) -> bool:
    """Create a new room with password protection."""
    url = f"{_get_room_url(room_code)}.json"

    data = {
        "password_hash": _hash_password(password),
        "creator": creator,
        "created_at": datetime.now().isoformat(),
        "athletes": {},
        "players": {}
    }

    try:
        response = requests.put(url, json=data, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


def verify_room_password(room_code: str, password: str) -> bool:
    """Verify if password is correct for a room."""
    data = get_room_data(room_code)
    if not data or "password_hash" not in data:
        return False
    return data["password_hash"] == _hash_password(password)


def room_exists(room_code: str) -> bool:
    """Check if a room exists."""
    url = f"{_get_room_url(room_code)}.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data is not None and "password_hash" in data
    except requests.RequestException:
        pass
    return False


def get_room_data(room_code: str) -> dict:
    """Get all data for a room."""
    url = f"{_get_room_url(room_code)}.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data:
                return data
    except requests.RequestException:
        pass
    return {}


def save_room_data(room_code: str, data: dict) -> bool:
    """Save room data to Firebase."""
    url = f"{_get_room_url(room_code)}.json"
    try:
        response = requests.put(url, json=data, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


def add_athlete(room_code: str, name: str, sport: str, country: str | None,
               matched_name: str | None, added_by: str, challenge_bonus: int = 0) -> bool:
    """Add an athlete to a room. Returns False if already exists."""
    data = get_room_data(room_code)

    # Check if athlete already exists (case-insensitive)
    name_lower = name.lower().strip()
    for key, athlete in data.get("athletes", {}).items():
        if athlete.get("name", "").lower().strip() == name_lower:
            return False

    # Add new athlete
    athlete = {
        "name": name,
        "sport": sport,
        "country": country,
        "matched_name": matched_name or name,
        "added_by": added_by,
        "added_at": datetime.now().isoformat(),
        "challenge_bonus": challenge_bonus,
    }

    if "athletes" not in data:
        data["athletes"] = {}

    # Use timestamp as key
    key = datetime.now().strftime("%Y%m%d%H%M%S%f")
    data["athletes"][key] = athlete

    return save_room_data(room_code, data)


def athlete_exists(room_code: str, name: str) -> bool:
    """Check if athlete exists in room."""
    data = get_room_data(room_code)
    name_lower = name.lower().strip()
    for athlete in data.get("athletes", {}).values():
        if athlete.get("name", "").lower().strip() == name_lower:
            return True
    return False


def get_athletes(room_code: str) -> list[dict]:
    """Get all athletes in a room, sorted newest first."""
    data = get_room_data(room_code)
    athletes_dict = data.get("athletes", {})
    # Include the Firebase key (timestamp-based) for reliable sorting
    athletes = []
    for key, val in athletes_dict.items():
        val["_key"] = key
        athletes.append(val)
    # Sort by added_at descending (newest first), fall back to key
    athletes.sort(key=lambda x: x.get("added_at", x.get("_key", "")), reverse=True)
    return athletes


def get_stats(room_code: str) -> dict[str, int]:
    """Get sport statistics for a room."""
    athletes = get_athletes(room_code)
    stats = {}
    for athlete in athletes:
        sport = athlete.get("sport", "Unknown")
        stats[sport] = stats.get(sport, 0) + 1
    return stats


def get_country_stats(room_code: str) -> dict[str, int]:
    """Get country statistics for a room."""
    athletes = get_athletes(room_code)
    stats = {}
    for athlete in athletes:
        country = athlete.get("country") or "Unknown"
        stats[country] = stats.get(country, 0) + 1
    return stats


def get_player_stats(room_code: str) -> dict[str, int]:
    """Get per-player statistics (who added how many)."""
    athletes = get_athletes(room_code)
    stats = {}
    for athlete in athletes:
        player = athlete.get("added_by", "Unknown")
        stats[player] = stats.get(player, 0) + 1
    return stats


def get_streak(room_code: str, player_name: str) -> tuple[int, int]:
    """Get current and best streak for a player in a room."""
    data = get_room_data(room_code)
    players = data.get("players", {})
    player_data = players.get(player_name, {})
    return player_data.get("current_streak", 0), player_data.get("best_streak", 0)


def increment_streak(room_code: str, player_name: str) -> tuple[int, int, bool]:
    """Increment streak for a player. Returns (current, best, is_new_record)."""
    data = get_room_data(room_code)

    if "players" not in data:
        data["players"] = {}
    if player_name not in data["players"]:
        data["players"][player_name] = {"current_streak": 0, "best_streak": 0}

    player_data = data["players"][player_name]
    player_data["current_streak"] = player_data.get("current_streak", 0) + 1

    current = player_data["current_streak"]
    best = player_data.get("best_streak", 0)

    is_new_record = current > best
    if is_new_record:
        player_data["best_streak"] = current
        best = current

    save_room_data(room_code, data)
    return current, best, is_new_record


def reset_streak(room_code: str, player_name: str) -> None:
    """Reset current streak for a player."""
    data = get_room_data(room_code)

    if "players" not in data:
        data["players"] = {}
    if player_name not in data["players"]:
        data["players"][player_name] = {"current_streak": 0, "best_streak": 0}

    data["players"][player_name]["current_streak"] = 0
    save_room_data(room_code, data)


def get_unique_counts(room_code: str) -> tuple[int, int, int, int, set, set]:
    """Get (total, unique_sports, unique_countries, unique_players, sports_set, countries_set) from one read."""
    athletes = get_athletes(room_code)
    sports = set()
    countries = set()
    players = set()
    for a in athletes:
        sports.add(a.get("sport", "Unknown"))
        country = a.get("country") or "Unknown"
        countries.add(country)
        players.add(a.get("added_by", "Unknown"))
    return len(athletes), len(sports), len(countries), len(players), sports, countries


def calculate_athlete_points(sport: str, country: str | None, athletes: list[dict]) -> tuple[int, int, int]:
    """Calculate points for an athlete based on rarity. Pure function, no Firebase calls.

    Returns (total_pts, sport_bonus, country_bonus).
    """
    total = len(athletes) or 1  # avoid division by zero

    # Count sport frequency
    sport_count = sum(1 for a in athletes if a.get("sport") == sport)
    sport_pct = sport_count / total * 100

    if sport_pct <= 2:
        sport_bonus = 4   # Epic
    elif sport_pct <= 5:
        sport_bonus = 3   # Rare
    elif sport_pct <= 15:
        sport_bonus = 2   # Uncommon
    elif sport_pct <= 30:
        sport_bonus = 1   # Common
    else:
        sport_bonus = 0   # Saturated

    # Count country frequency
    country_bonus = 0
    if country:
        country_count = sum(1 for a in athletes if a.get("country") == country)
        country_pct = country_count / total * 100

        if country_pct <= 2:
            country_bonus = 2
        elif country_pct <= 5:
            country_bonus = 1
        else:
            country_bonus = 0

    total_pts = 1 + sport_bonus + country_bonus  # base 1
    return total_pts, sport_bonus, country_bonus


def get_player_scores(room_code: str) -> dict[str, dict]:
    """Get per-player scores from one Firebase read.

    Returns {player_name: {"total_pts": int, "count": int, "avg": float}}.
    """
    athletes = get_athletes(room_code)
    if not athletes:
        return {}

    # Group athletes by player
    player_athletes: dict[str, list[dict]] = {}
    for a in athletes:
        player = a.get("added_by", "Unknown")
        player_athletes.setdefault(player, []).append(a)

    scores: dict[str, dict] = {}
    for player, p_athletes in player_athletes.items():
        total_pts = 0
        for a in p_athletes:
            pts, _, _ = calculate_athlete_points(a.get("sport", ""), a.get("country"), athletes)
            challenge_bonus = a.get("challenge_bonus", 0)
            total_pts += pts + challenge_bonus
        count = len(p_athletes)
        scores[player] = {
            "total_pts": total_pts,
            "count": count,
            "avg": round(total_pts / count, 1) if count else 0,
        }

    return scores


def clear_room(room_code: str) -> None:
    """Clear all data in a room."""
    save_room_data(room_code, {"athletes": {}, "players": {}, "password_hash": get_room_data(room_code).get("password_hash", "")})
