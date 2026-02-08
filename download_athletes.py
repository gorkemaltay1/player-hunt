"""Download all athletes from Wikidata and store locally."""

import json
import requests
from pathlib import Path
import time

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
OUTPUT_FILE = Path(__file__).parent / "athletes_db.json"

HEADERS = {
    "User-Agent": "SportsCounter/1.0 (https://example.com; contact@example.com)",
    "Accept": "application/json"
}

# Sports occupations to query (split into batches)
OCCUPATIONS = [
    ("Football", "wd:Q937857"),      # footballer
    ("Basketball", "wd:Q3665646"),   # basketball player
    ("Tennis", "wd:Q10833314"),      # tennis player
    ("Cricket", "wd:Q12299841"),     # cricketer
    ("Golf", "wd:Q13381863"),        # golfer
    ("Baseball", "wd:Q10871364"),    # baseball player
    ("Athletics", "wd:Q11513337"),   # athletics competitor
    ("Boxing", "wd:Q11338576"),      # boxer
    ("Hockey", "wd:Q13141064"),      # ice hockey player
    ("Swimming", "wd:Q10843402"),    # swimmer
    ("Motorsport", "wd:Q18515558"),  # racing driver
    ("Cycling", "wd:Q15117302"),     # cyclist
    ("Rugby", "wd:Q13382519"),       # rugby player
    ("Gymnastics", "wd:Q2309784"),   # gymnast
    ("Volleyball", "wd:Q15982795"), # volleyball player
    ("Judo", "wd:Q11774891"),        # judoka
    ("Chess", "wd:Q10873124"),       # chess player
    ("Skiing", "wd:Q13381376"),      # skier
    ("MMA", "wd:Q17351648"),         # MMA fighter
    ("Figure Skating", "wd:Q4009406"), # figure skater
    ("Wrestling", "wd:Q13382608"),   # wrestler
    ("Badminton", "wd:Q13382566"),   # badminton player
    ("Table Tennis", "wd:Q12840545"), # table tennis player
    ("Fencing", "wd:Q13381689"),     # fencer
    ("Archery", "wd:Q10556138"),     # archer
    ("Weightlifting", "wd:Q13382487"), # weightlifter
    ("Diving", "wd:Q2492883"),       # diver
    ("Rowing", "wd:Q13382122"),      # rower
    ("Skateboarding", "wd:Q18939491"), # skateboarder
    ("Surfing", "wd:Q13561328"),     # surfer
    ("Snowboarding", "wd:Q18924081"), # snowboarder
    ("Esports", "wd:Q19799266"),     # esports player
    ("Triathlon", "wd:Q18536342"),   # triathlete
]


def query_occupation(sport_name, occupation_id):
    """Query athletes for a specific occupation."""
    query = f"""
    SELECT ?item ?itemLabel ?countryLabel WHERE {{
      ?item wdt:P106 {occupation_id} .
      OPTIONAL {{ ?item wdt:P27 ?country . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """

    try:
        response = requests.get(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=120
        )
        response.raise_for_status()
        return response.json().get("results", {}).get("bindings", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []


def download_athletes():
    """Download athletes from Wikidata."""
    print("Downloading athletes from Wikidata...")
    print(f"Total sports to query: {len(OCCUPATIONS)}")
    print()

    athletes = {}
    total = 0

    for sport_name, occupation_id in OCCUPATIONS:
        print(f"Downloading {sport_name}...", end=" ", flush=True)

        results = query_occupation(sport_name, occupation_id)
        count = 0

        for row in results:
            name = row.get("itemLabel", {}).get("value", "")
            country = row.get("countryLabel", {}).get("value", "")

            if not name or name.startswith("Q"):
                continue

            key = name.lower()

            if key not in athletes:
                athletes[key] = {
                    "name": name,
                    "sport": sport_name,
                    "country": country if not country.startswith("Q") else ""
                }
                count += 1

        print(f"{count} athletes")
        total += count
        time.sleep(1)  # Rate limiting

    print()
    print(f"Total unique athletes: {len(athletes)}")

    # Save to file
    print(f"Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(athletes, f, ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"Done! File size: {size_mb:.1f} MB")
    return True


if __name__ == "__main__":
    download_athletes()
