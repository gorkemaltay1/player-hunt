"""Wikidata API integration for athlete sport and country detection."""

import sqlite3
import requests
from pathlib import Path

HEADERS = {
    "User-Agent": "SportsCounter/1.0 (https://example.com; contact@example.com)"
}

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
LOCAL_DB_FILE = Path(__file__).parent / "athletes_db.sqlite"

# Wikidata property IDs
P_SPORT = "P641"           # sport
P_OCCUPATION = "P106"      # occupation
P_COUNTRY = "P27"          # country of citizenship
P_INSTANCE_OF = "P31"      # instance of (to check if human)

# Cache for Q-code to label mapping
_label_cache = {}

# Famous athletes with common single-word names
FAMOUS_ATHLETES = {
    "nadal": "Rafael Nadal",
    "federer": "Roger Federer",
    "djokovic": "Novak Djokovic",
    "messi": "Lionel Messi",
    "ronaldo": "Cristiano Ronaldo",
    "neymar": "Neymar",
    "lebron": "LeBron James",
    "kobe": "Kobe Bryant",
    "jordan": "Michael Jordan",
    "serena": "Serena Williams",
    "venus": "Venus Williams",
    "tiger": "Tiger Woods",
    "bolt": "Usain Bolt",
    "phelps": "Michael Phelps",
    "sharapova": "Maria Sharapova",
    "beckham": "David Beckham",
    "zidane": "Zinedine Zidane",
    "maradona": "Diego Maradona",
    "pele": "Pelé",
    "tyson": "Mike Tyson",
    "ali": "Muhammad Ali",
    "schumacher": "Michael Schumacher",
    "hamilton": "Lewis Hamilton",
    "verstappen": "Max Verstappen",
    "curry": "Stephen Curry",
    "durant": "Kevin Durant",
    "mbappe": "Kylian Mbappé",
    "haaland": "Erling Haaland",
    "modric": "Luka Modrić",
    "benzema": "Karim Benzema",
}


def lookup_athlete(athlete_name: str) -> dict | None:
    """
    Look up an athlete - first in local database, then Wikidata API.

    Returns:
        Dict with 'sport', 'country', and 'matched_name' keys, or None if not found.
    """
    name = athlete_name.strip()
    is_single_word = " " not in name

    # Step 0: Check famous athletes shortcut
    if name.lower() in FAMOUS_ATHLETES:
        full_name = FAMOUS_ATHLETES[name.lower()]
        # Try to find the full name
        result = _search_local_exact(full_name)
        if result:
            return result
        result = _lookup_via_api(full_name)
        if result:
            return result

    # Step 1: Try local database exact match (instant!)
    local_result = _search_local_exact(name)
    if local_result:
        return local_result

    # Step 2: For single-word queries, try Wikidata API first (better ranking)
    # For multi-word queries, local partial match is more reliable
    if is_single_word:
        api_result = _lookup_via_api(name)
        if api_result:
            return api_result

        # Fallback to local partial match for single words
        local_partial = _search_local_partial(name)
        if local_partial:
            return local_partial
    else:
        # Multi-word: try local partial first, then API
        local_partial = _search_local_partial(name)
        if local_partial:
            return local_partial

        api_result = _lookup_via_api(name)
        if api_result:
            return api_result

    return None


def _search_local_exact(name: str) -> dict | None:
    """Search for exact match in local SQLite database."""
    if not LOCAL_DB_FILE.exists():
        return None

    key = name.lower().strip()

    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, sport, country FROM athletes WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "sport": row[1],
                "country": _normalize_country(row[2]) if row[2] else None,
                "matched_name": row[0]
            }
    except sqlite3.Error:
        pass

    return None


def _search_local_partial(name: str) -> dict | None:
    """Search for partial match in local SQLite database."""
    if not LOCAL_DB_FILE.exists():
        return None

    key = name.lower().strip()

    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()

        # Try matching last name (e.g., "federer" -> "roger federer")
        cursor.execute(
            "SELECT name, sport, country FROM athletes WHERE key LIKE ? ORDER BY length(key) ASC LIMIT 1",
            (f"% {key}",)
        )
        row = cursor.fetchone()

        conn.close()

        if row:
            return {
                "sport": row[1],
                "country": _normalize_country(row[2]) if row[2] else None,
                "matched_name": row[0]
            }
    except sqlite3.Error:
        pass

    return None


def _lookup_via_api(name: str) -> dict | None:
    """Look up athlete via Wikidata API."""
    search_result = _search_entity(name)
    if not search_result:
        return None

    entity_id, matched_name = search_result

    entity_data = _get_entity(entity_id)
    if not entity_data:
        return None

    claims = entity_data.get("claims", {})

    sport = _extract_sport(claims)
    if not sport:
        return None

    country = _extract_country(claims)

    return {"sport": sport, "country": country, "matched_name": matched_name}


def _search_entity(name: str) -> tuple[str, str] | None:
    """Search for an entity by name and return its Q-ID and matched label."""
    # Try multiple search variations
    search_terms = [name]

    # Add variation without double letters
    if any(c*2 in name.lower() for c in 'abcdefghijklmnopqrstuvwxyz'):
        for c in 'abcdefghijklmnopqrstuvwxyz':
            if c*2 in name.lower():
                search_terms.append(name.lower().replace(c*2, c))

    for search_term in search_terms:
        params = {
            "action": "wbsearchentities",
            "search": search_term,
            "language": "en",
            "type": "item",
            "limit": 5,
            "format": "json"
        }

        result = _do_search(params)
        if result:
            return result

    return None


def _do_search(params: dict) -> tuple[str, str] | None:
    """Execute search with given params."""
    try:
        response = requests.get(WIKIDATA_API, params=params, headers=HEADERS, timeout=(2, 5))
        if response.status_code != 200:
            return None

        data = response.json()
        results = data.get("search", [])

        if not results:
            return None

        search_term = params.get("search", "")

        # Keywords that indicate this is an actual athlete (person)
        athlete_keywords = ["player", "footballer", "basketball player", "tennis player",
                          "athlete", "swimmer", "boxer", "golfer", "cyclist", "skier",
                          "runner", "olympic", "champion", "racing driver", "gymnast",
                          "volleyball player", "cricketer", "baseball player", "judoka",
                          "chess player", "wrestler", "skateboarder", "surfer"]

        # Keywords that indicate this is NOT a person (skip these)
        skip_keywords = ["rivalry", "match", "tournament", "championship", "game",
                        "season", "team", "club", "stadium", "award", "record",
                        "film", "song", "album", "book", "series", "episode"]

        # First pass: find actual athletes
        for result in results:
            entity_id = result.get("id")
            matched_name = result.get("label", search_term)
            description = result.get("description", "").lower()

            # Skip non-person entries
            if any(skip in description for skip in skip_keywords):
                continue

            # Check if description suggests this is an athlete
            if any(kw in description for kw in athlete_keywords):
                return (entity_id, matched_name)

        # Second pass: find any person that might be an athlete
        for result in results:
            description = result.get("description", "").lower()

            # Skip non-person entries
            if any(skip in description for skip in skip_keywords):
                continue

            # Accept if it looks like a person (has birth year pattern or nationality)
            if "born" in description or any(nat in description for nat in
                ["american", "british", "french", "german", "spanish", "italian",
                 "brazilian", "argentine", "japanese", "chinese", "russian",
                 "australian", "canadian", "swiss", "dutch", "portuguese"]):
                return (result.get("id"), result.get("label", search_term))

        # Last resort: return first result that's not in skip list
        for result in results:
            description = result.get("description", "").lower()
            if not any(skip in description for skip in skip_keywords):
                return (result.get("id"), result.get("label", search_term))

        return None

    except requests.RequestException:
        return None


def _get_entity(entity_id: str) -> dict | None:
    """Get entity data by Q-ID."""
    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "claims|labels",
        "languages": "en",
        "format": "json"
    }

    try:
        response = requests.get(WIKIDATA_API, params=params, headers=HEADERS, timeout=(2, 5))
        if response.status_code != 200:
            return None

        data = response.json()
        entities = data.get("entities", {})

        return entities.get(entity_id)

    except requests.RequestException:
        return None


def _extract_sport(claims: dict) -> str | None:
    """Extract sport from entity claims."""
    # First try P641 (sport)
    if P_SPORT in claims:
        sport_claims = claims[P_SPORT]
        if sport_claims:
            sport_id = sport_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if sport_id:
                sport = _get_label(sport_id)
                if sport:
                    return _normalize_sport(sport)

    # Fallback: check occupation (P106) for sport-related occupations
    if P_OCCUPATION in claims:
        for claim in claims[P_OCCUPATION]:
            occupation_id = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if occupation_id:
                occupation = _get_label(occupation_id)
                if occupation:
                    sport = _occupation_to_sport(occupation)
                    if sport:
                        return sport

    return None


def _normalize_sport(sport: str) -> str:
    """Normalize sport names for consistency."""
    sport_lower = sport.lower()

    normalizations = {
        "association football": "Football",
        "football": "Football",
        "soccer": "Football",
        "basketball": "Basketball",
        "tennis": "Tennis",
        "cricket": "Cricket",
        "golf": "Golf",
        "baseball": "Baseball",
        "ice hockey": "Hockey",
        "swimming": "Swimming",
        "athletics": "Athletics",
        "track and field": "Athletics",
        "boxing": "Boxing",
        "mixed martial arts": "MMA",
        "rugby union": "Rugby",
        "rugby league": "Rugby",
        "cycling": "Cycling",
        "artistic gymnastics": "Gymnastics",
        "gymnastics": "Gymnastics",
        "volleyball": "Volleyball",
        "skateboarding": "Skateboarding",
        "surfing": "Surfing",
        "snowboarding": "Snowboarding",
        "chess": "Chess",
        "formula one": "Formula 1",
        "formula one racing": "Formula 1",
        "kart racing": "Motorsport",
        "auto racing": "Motorsport",
        "motorcycle racing": "Motorsport",
        "rallying": "Motorsport",
        "alpine skiing": "Skiing",
        "figure skating": "Figure Skating",
        "badminton": "Badminton",
        "table tennis": "Table Tennis",
    }

    if sport_lower in normalizations:
        return normalizations[sport_lower]

    # Default: title case
    return sport.title()


def _extract_country(claims: dict) -> str | None:
    """Extract country of citizenship from entity claims."""
    if P_COUNTRY in claims:
        country_claims = claims[P_COUNTRY]
        if country_claims:
            country_id = country_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if country_id:
                country = _get_label(country_id)
                if country:
                    return _normalize_country(country)

    return None


def _normalize_country(country: str) -> str:
    """Normalize country names for consistency."""
    normalizations = {
        "United States of America": "USA",
        "United States": "USA",
        "United Kingdom": "UK",
        "Kingdom of the Netherlands": "Netherlands",
        "People's Republic of China": "China",
        "Republic of Korea": "South Korea",
        "Democratic People's Republic of Korea": "North Korea",
        "Russian Federation": "Russia",
        "Czech Republic": "Czechia",
    }

    return normalizations.get(country, country)


def _get_label(entity_id: str) -> str | None:
    """Get the English label for a Q-ID."""
    if entity_id in _label_cache:
        return _label_cache[entity_id]

    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "labels",
        "languages": "en",
        "format": "json"
    }

    try:
        response = requests.get(WIKIDATA_API, params=params, headers=HEADERS, timeout=(2, 5))
        if response.status_code != 200:
            return None

        data = response.json()
        entities = data.get("entities", {})
        entity = entities.get(entity_id, {})
        labels = entity.get("labels", {})
        en_label = labels.get("en", {}).get("value")

        if en_label:
            _label_cache[entity_id] = en_label

        return en_label

    except requests.RequestException:
        return None


def _occupation_to_sport(occupation: str) -> str | None:
    """Map occupation to sport name."""
    occupation_lower = occupation.lower()

    mappings = {
        "footballer": "Football",
        "association football player": "Football",
        "soccer player": "Football",
        "basketball player": "Basketball",
        "tennis player": "Tennis",
        "cricketer": "Cricket",
        "golfer": "Golf",
        "baseball player": "Baseball",
        "ice hockey player": "Hockey",
        "field hockey player": "Hockey",
        "swimmer": "Swimming",
        "sprinter": "Athletics",
        "marathon runner": "Athletics",
        "long-distance runner": "Athletics",
        "track and field athlete": "Athletics",
        "boxer": "Boxing",
        "mixed martial artist": "MMA",
        "rugby player": "Rugby",
        "rugby union player": "Rugby",
        "cyclist": "Cycling",
        "racing driver": "Motorsport",
        "Formula One driver": "Formula 1",
        "gymnast": "Gymnastics",
        "volleyball player": "Volleyball",
        "wrestler": "Wrestling",
        "alpine skier": "Skiing",
        "figure skater": "Skating",
        "skateboarder": "Skateboarding",
        "surfer": "Surfing",
        "snowboarder": "Snowboarding",
        "badminton player": "Badminton",
        "table tennis player": "Table Tennis",
        "fencer": "Fencing",
        "archer": "Archery",
        "weightlifter": "Weightlifting",
        "diver": "Diving",
        "rower": "Rowing",
        "judoka": "Judo",
        "chess player": "Chess",
        "esports player": "Esports",
        "triathlete": "Triathlon",
    }

    for key, sport in mappings.items():
        if key.lower() in occupation_lower:
            return sport

    # If occupation contains "player" or "athlete", return the occupation itself
    if "player" in occupation_lower or "athlete" in occupation_lower:
        return occupation.replace(" player", "").title()

    return None


def get_supported_sports() -> list[str]:
    """Return list of sports we can detect (for UI display)."""
    return [
        "Football", "Basketball", "Tennis", "Cricket", "Golf", "Baseball",
        "Hockey", "Swimming", "Athletics", "Boxing", "MMA", "Rugby",
        "Cycling", "Formula 1", "Motorsport", "Gymnastics", "Volleyball",
        "Wrestling", "Skiing", "Skating", "Skateboarding", "Surfing",
        "Snowboarding", "Badminton", "Table Tennis", "Fencing", "Archery",
        "Weightlifting", "Diving", "Rowing", "Judo", "Chess", "Esports",
        "Triathlon", "... and more (auto-detected from Wikidata)"
    ]


def get_total_countries() -> int:
    """Return the number of distinct countries in the local athlete database."""
    if not LOCAL_DB_FILE.exists():
        return 0
    try:
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT country) FROM athletes WHERE country IS NOT NULL")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error:
        return 0


# For backwards compatibility
SPORT_KEYWORDS = {sport: [] for sport in get_supported_sports()[:-1]}
