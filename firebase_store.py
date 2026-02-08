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
               matched_name: str | None, added_by: str) -> bool:
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
        "added_at": datetime.now().isoformat()
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
    """Get all athletes in a room."""
    data = get_room_data(room_code)
    athletes = list(data.get("athletes", {}).values())
    # Sort by added_at
    athletes.sort(key=lambda x: x.get("added_at", ""), reverse=True)
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


def get_unique_counts(room_code: str) -> tuple[int, int, int, int, set]:
    """Get (total, unique_sports, unique_countries, unique_players, sports_set) from one read."""
    athletes = get_athletes(room_code)
    sports = set()
    countries = set()
    players = set()
    for a in athletes:
        sports.add(a.get("sport", "Unknown"))
        country = a.get("country") or "Unknown"
        countries.add(country)
        players.add(a.get("added_by", "Unknown"))
    return len(athletes), len(sports), len(countries), len(players), sports


def clear_room(room_code: str) -> None:
    """Clear all data in a room."""
    save_room_data(room_code, {"athletes": {}, "players": {}, "password_hash": get_room_data(room_code).get("password_hash", "")})
