"""Player Hunt - Multiplayer Sports Athlete Guessing Game."""

import streamlit as st
import altair as alt
import pandas as pd
import random as _rng
from datetime import datetime, timedelta

from athlete_lookup import lookup_athlete, get_supported_sports, get_total_countries, get_random_suggestions
from firebase_store import (
    add_athlete, athlete_exists, get_athletes, get_stats, get_country_stats,
    get_player_stats, get_streak, increment_streak, reset_streak, clear_room,
    generate_room_code, create_room, verify_room_password, room_exists,
    get_unique_counts, get_room_data, calculate_athlete_points, get_player_scores,
    heartbeat, get_active_players
)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_lookup(name: str) -> dict | None:
    """Cached athlete lookup to avoid repeated API calls."""
    return lookup_athlete(name)


# --- Continent mapping for challenges ---
CONTINENT_MAP = {
    "Europe": ["UK", "France", "Germany", "Spain", "Italy", "Netherlands", "Belgium",
               "Portugal", "Sweden", "Norway", "Denmark", "Finland", "Switzerland",
               "Austria", "Poland", "Czech Republic", "Greece", "Hungary", "Romania",
               "Croatia", "Serbia", "Ireland", "Scotland", "Wales", "Ukraine",
               "Russia", "Turkey", "Bulgaria", "Slovakia", "Slovenia", "Lithuania",
               "Latvia", "Estonia", "Iceland", "Luxembourg", "Montenegro", "Albania",
               "North Macedonia", "Bosnia and Herzegovina", "Moldova", "Belarus",
               "United Kingdom", "Great Britain"],
    "Asia": ["China", "Japan", "South Korea", "India", "Turkey", "Iran", "Iraq",
             "Saudi Arabia", "Thailand", "Vietnam", "Philippines", "Indonesia",
             "Malaysia", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal",
             "Myanmar", "Cambodia", "Laos", "Mongolia", "Kazakhstan", "Uzbekistan",
             "Singapore", "Taiwan", "Hong Kong", "Israel", "Lebanon", "Jordan",
             "Syria", "Afghanistan", "North Korea", "United Arab Emirates", "Qatar",
             "Bahrain", "Kuwait", "Oman", "Yemen", "Turkmenistan", "Kyrgyzstan",
             "Tajikistan", "Armenia", "Azerbaijan", "Georgia"],
    "Africa": ["South Africa", "Nigeria", "Kenya", "Egypt", "Ethiopia", "Ghana",
               "Cameroon", "Senegal", "Morocco", "Algeria", "Tunisia", "Ivory Coast",
               "Tanzania", "Uganda", "Zimbabwe", "Mozambique", "Angola", "Zambia",
               "Mali", "Burkina Faso", "Niger", "Congo", "DR Congo",
               "Democratic Republic of the Congo", "Madagascar", "Sudan",
               "Somalia", "Eritrea", "Namibia", "Botswana", "Rwanda", "Togo", "Benin",
               "Sierra Leone", "Liberia", "Gabon", "Gambia", "Guinea", "Libya"],
    "North America": ["USA", "Canada", "Mexico", "Cuba", "Jamaica", "Haiti",
                      "Dominican Republic", "Puerto Rico", "Trinidad and Tobago",
                      "Costa Rica", "Panama", "Honduras", "El Salvador", "Guatemala",
                      "Nicaragua", "Bahamas", "Barbados", "United States",
                      "United States of America"],
    "South America": ["Brazil", "Argentina", "Colombia", "Chile", "Peru", "Venezuela",
                      "Ecuador", "Bolivia", "Uruguay", "Paraguay", "Guyana", "Suriname"],
    "Oceania": ["Australia", "New Zealand", "Fiji", "Papua New Guinea", "Samoa",
                "Tonga", "Vanuatu", "Solomon Islands"],
}

# Reverse lookup: country → continent
_COUNTRY_TO_CONTINENT: dict[str, str] = {}
for _cont, _countries in CONTINENT_MAP.items():
    for _c in _countries:
        _COUNTRY_TO_CONTINENT[_c] = _cont


def _format_relative_time(iso_timestamp: str) -> str:
    """Convert ISO timestamp to relative time string."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        diff = datetime.now() - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            m = seconds // 60
            return f"{m}m ago"
        elif seconds < 86400:
            h = seconds // 3600
            return f"{h}h ago"
        else:
            d = seconds // 86400
            return f"{d}d ago"
    except (ValueError, TypeError):
        return ""


def generate_challenge(found_sports_set: set) -> dict:
    """Generate a random challenge, biased toward missing sports."""
    all_sports = get_supported_sports()[:-1]
    missing = [s for s in all_sports if s not in found_sports_set]
    continents = list(CONTINENT_MAP.keys())

    # Pick challenge type: sport (40%), continent (30%), combo (30%)
    roll = _rng.random()

    if roll < 0.4:
        # Sport challenge
        pool = missing if missing else all_sports
        sport = _rng.choice(pool)
        return {"type": "sport", "sport": sport, "bonus": 3,
                "text": f"Find a **{sport}** athlete"}
    elif roll < 0.7:
        # Continent challenge
        continent = _rng.choice(continents)
        return {"type": "continent", "continent": continent, "bonus": 3,
                "text": f"Add an athlete from **{continent}**"}
    else:
        # Combo challenge
        pool = missing if missing else all_sports
        sport = _rng.choice(pool)
        continent = _rng.choice(continents)
        return {"type": "combo", "sport": sport, "continent": continent, "bonus": 5,
                "text": f"Find a **{sport}** athlete from **{continent}**"}


def check_challenge(challenge: dict | None, sport: str, country: str | None) -> bool:
    """Check if an added athlete satisfies the active challenge."""
    if not challenge:
        return False

    ctype = challenge["type"]
    if ctype == "sport":
        return sport == challenge["sport"]
    elif ctype == "continent":
        target_continent = challenge["continent"]
        if not country:
            return False
        return _COUNTRY_TO_CONTINENT.get(country) == target_continent
    elif ctype == "combo":
        if sport != challenge["sport"]:
            return False
        if not country:
            return False
        return _COUNTRY_TO_CONTINENT.get(country) == challenge["continent"]
    return False


st.set_page_config(
    page_title="Player Hunt",
    page_icon="🎯",
    layout="wide"
)

# Session state initialization — restore from URL query params on refresh
_qp = st.query_params
if "room_code" not in st.session_state:
    _url_room = _qp.get("room", None)
    if _url_room and room_exists(_url_room):
        st.session_state.room_code = _url_room
    else:
        st.session_state.room_code = None
if "player_name" not in st.session_state:
    st.session_state.player_name = _qp.get("player", None)
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "active_challenge" not in st.session_state:
    st.session_state.active_challenge = None

# Login/Join Room Screen
if not st.session_state.room_code or not st.session_state.player_name:
    st.title("🎯 Player Hunt")
    st.markdown("### Multiplayer Athlete Guessing Game")

    st.divider()

    tab1, tab2 = st.tabs(["🎮 Join Room", "➕ Create Room"])

    with tab1:
        st.subheader("Join an Existing Room")

        join_room = st.text_input("Room Code", placeholder="e.g., ABC123", key="join_room", max_chars=6)
        join_password = st.text_input("Room Password", type="password", key="join_password")
        join_name = st.text_input("Your Name", placeholder="e.g., John", key="join_name")

        if st.button("Join Game", type="primary", use_container_width=True):
            if join_room and join_password and join_name:
                room_code = join_room.upper().strip()

                if not room_exists(room_code):
                    st.error("Room not found! Check the room code.")
                elif not verify_room_password(room_code, join_password):
                    st.error("Wrong password!")
                else:
                    st.session_state.room_code = room_code
                    st.session_state.player_name = join_name.strip()
                    st.query_params.update({"room": room_code, "player": join_name.strip()})
                    heartbeat(room_code, join_name.strip())
                    st.success("Joining room...")
                    st.rerun()
            else:
                st.error("Please fill in all fields!")

    with tab2:
        st.subheader("Create a New Room")

        # Auto-generate room code
        if "new_room_code" not in st.session_state:
            st.session_state.new_room_code = generate_room_code()

        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_input("Room Code (auto-generated)", value=st.session_state.new_room_code, disabled=True, key="display_code")
        with col2:
            if st.button("🔄", help="Generate new code"):
                st.session_state.new_room_code = generate_room_code()
                st.rerun()

        create_password = st.text_input("Set Password", type="password", key="create_password", placeholder="Password for your room")
        create_password2 = st.text_input("Confirm Password", type="password", key="create_password2", placeholder="Confirm password")
        create_name = st.text_input("Your Name", placeholder="e.g., John", key="create_name")

        if st.button("Create Room", type="primary", use_container_width=True):
            if create_password and create_name:
                if create_password != create_password2:
                    st.error("Passwords don't match!")
                elif len(create_password) < 3:
                    st.error("Password must be at least 3 characters!")
                else:
                    room_code = st.session_state.new_room_code

                    if room_exists(room_code):
                        # Very unlikely, but generate a new code
                        st.session_state.new_room_code = generate_room_code()
                        st.error("Room code already exists. Please try again.")
                        st.rerun()
                    else:
                        if create_room(room_code, create_password, create_name.strip()):
                            st.session_state.room_code = room_code
                            st.session_state.player_name = create_name.strip()
                            st.query_params.update({"room": room_code, "player": create_name.strip()})
                            heartbeat(room_code, create_name.strip())
                            st.success(f"Room **{room_code}** created! Share this code with friends.")
                            st.rerun()
                        else:
                            st.error("Failed to create room. Please try again.")
            else:
                st.error("Please fill in all fields!")

    st.divider()

    st.markdown("""
    ### How to Play
    1. **Create a room** and share the code + password with friends
    2. **Enter athlete names** to earn points
    3. **Build streaks** for consecutive correct answers
    4. **Compete** on the leaderboard!
    """)

    st.stop()

# Main Game Screen
room_code = st.session_state.room_code
player_name = st.session_state.player_name

# Header with room info
header_col1, header_col2, header_col3 = st.columns([2, 1, 1])

with header_col1:
    st.title("🎯 Player Hunt")

with header_col2:
    st.metric("Room", room_code)

with header_col3:
    st.metric("Player", player_name)
    if st.button("Leave", use_container_width=True):
        st.session_state.room_code = None
        st.session_state.player_name = None
        st.session_state.last_result = None
        st.session_state.active_challenge = None
        st.query_params.clear()
        st.rerun()

# Active Players (auto-refresh heartbeat every 10 seconds)
@st.fragment(run_every=timedelta(seconds=10))
def active_players_section():
    rc = st.session_state.room_code
    pn = st.session_state.player_name
    heartbeat(rc, pn)
    active = get_active_players(rc)
    if active:
        names = []
        for p in active:
            if p["name"] == pn:
                names.append(f"**{p['name']}** (You)")
            else:
                names.append(f"**{p['name']}**")
        st.markdown(f"🟢 **Online** ({len(active)}): {' · '.join(names)}")

active_players_section()

# Streak Display
current_streak, best_streak = get_streak(room_code, player_name)

streak_col1, streak_col2, streak_col3 = st.columns([1, 1, 2])

with streak_col1:
    if current_streak >= 5:
        st.metric("Your Streak", f"{current_streak} 🔥")
    elif current_streak >= 3:
        st.metric("Your Streak", f"{current_streak} ⚡")
    else:
        st.metric("Your Streak", current_streak)

with streak_col2:
    st.metric("Your Best", f"{best_streak} 🏆" if best_streak > 0 else "0")

st.divider()

# Preload room counts (single Firebase read)
total, unique_sports, unique_countries, unique_players, found_sports_set, found_countries_set = get_unique_counts(room_code)

# Dynamic suggestion tip — real athlete suggestions from local DB
_existing_names = set()
if total > 0:
    _room_athletes = get_athletes(room_code)
    _existing_names = {a.get("name", "").lower().strip() for a in _room_athletes}

_suggestions = get_random_suggestions(_existing_names, count=5)
if _suggestions:
    _pick = _rng.choice(_suggestions)
    st.info(f"💡 Try a **{_pick['sport']}** player from **{_pick['country']}**!")

# Challenge Card
if st.session_state.active_challenge is None:
    st.session_state.active_challenge = generate_challenge(found_sports_set)

challenge = st.session_state.active_challenge
ch_col1, ch_col2 = st.columns([5, 1])
with ch_col1:
    st.markdown(
        f"🎯 **Challenge:** {challenge['text']} — **+{challenge['bonus']} bonus pts**"
    )
with ch_col2:
    if st.button("🔄 New", key="reroll_challenge", help="Get a new challenge"):
        st.session_state.active_challenge = generate_challenge(found_sports_set)
        st.rerun()

# Input Section
header_col1, header_col2 = st.columns([6, 1])

with header_col1:
    st.header("Add Athlete")

with header_col2:
    with st.popover("ℹ️ Supported Sports"):
        st.markdown("**We can detect these sports:**")
        sports_list = get_supported_sports()
        mid = len(sports_list) // 2 + len(sports_list) % 2
        col_a, col_b = st.columns(2)
        with col_a:
            for sport in sports_list[:mid]:
                st.write(f"• {sport}")
        with col_b:
            for sport in sports_list[mid:]:
                st.write(f"• {sport}")
        st.caption("Powered by Wikidata")

# Form for Enter key support
with st.form(key="athlete_form", clear_on_submit=True):
    col1, col2 = st.columns([3, 1])

    with col1:
        athlete_name = st.text_input(
            "Athlete Name",
            placeholder="e.g., LeBron James, Serena Williams, Lionel Messi",
            label_visibility="collapsed"
        )

    with col2:
        submitted = st.form_submit_button("Add Athlete", type="primary", use_container_width=True)

# Process new athlete
if submitted and athlete_name:
    name = athlete_name.strip()

    if athlete_exists(room_code, name):
        st.session_state.last_result = {"type": "warning", "message": f"**{name}** is already in the list!"}
    else:
        result = cached_lookup(name)

        if result:
            sport = result["sport"]
            country = result.get("country")
            matched_name = result.get("matched_name", name)

            # Check challenge
            active_ch = st.session_state.active_challenge
            challenge_completed = check_challenge(active_ch, sport, country)
            ch_bonus = active_ch["bonus"] if challenge_completed else 0

            # Calculate rarity points
            existing_athletes = get_athletes(room_code)
            pts, s_bonus, c_bonus = calculate_athlete_points(sport, country, existing_athletes)
            total_pts = pts + ch_bonus

            # Add to Firebase
            add_athlete(room_code, name, sport, country, matched_name, player_name,
                        challenge_bonus=ch_bonus)
            current, best, is_record = increment_streak(room_code, player_name)

            # Generate new challenge if completed
            if challenge_completed:
                st.session_state.active_challenge = generate_challenge(found_sports_set)

            # Store result for display
            st.session_state.last_result = {
                "type": "success",
                "input": name,
                "matched": matched_name,
                "sport": sport,
                "country": country,
                "streak": current,
                "is_record": is_record,
                "points": total_pts,
                "sport_bonus": s_bonus,
                "country_bonus": c_bonus,
                "challenge_completed": challenge_completed,
                "challenge_bonus": ch_bonus,
            }
        else:
            reset_streak(room_code, player_name)
            st.session_state.last_result = {"type": "error", "message": f"Could not find '{name}'. Streak reset! 💔"}

# Show last result as preview card
if st.session_state.last_result:
    result = st.session_state.last_result

    if result["type"] == "success":
        # Preview card with Wikipedia link — 4 columns
        prev_col1, prev_col2, prev_col3, prev_col4 = st.columns(4)

        # Athlete with Wikipedia link
        wiki_url = "https://en.wikipedia.org/wiki/" + result["matched"].replace(" ", "_")
        prev_col1.markdown("**Athlete**")
        prev_col1.markdown(f"### [{result['matched']}]({wiki_url})")

        prev_col2.metric("Sport", result["sport"])
        prev_col3.metric("Country", result["country"] or "—")

        pts_display = f"+{result.get('points', 1)} pts"
        prev_col4.metric("Points", pts_display)

        # Challenge completion celebration
        if result.get("challenge_completed"):
            st.success(f"🎯 **Challenge Complete!** +{result['challenge_bonus']} bonus points!")
            st.balloons()

        # Success message with streak
        if result["is_record"] and result["streak"] > 1:
            st.success(f"✓ Added by {player_name}! 🎉 NEW RECORD: {result['streak']} streak!")
            if not result.get("challenge_completed"):
                st.balloons()
        elif result["streak"] >= 5:
            st.success(f"✓ Added by {player_name}! 🔥 {result['streak']} streak!")
        elif result["streak"] >= 3:
            st.success(f"✓ Added by {player_name}! ⚡ {result['streak']} streak!")
        else:
            st.success(f"✓ Added by {player_name}!")

    elif result["type"] == "warning":
        st.warning(result["message"])

    elif result["type"] == "error":
        st.error(result["message"])

# Milestone Progress Bar
milestones = [10, 25, 50, 100, 150, 200, 300, 500]

if total > 0:
    next_milestone = next((m for m in milestones if m > total), milestones[-1])
    prev_milestone = max((m for m in milestones if m <= total), default=0)
    progress = min(total / next_milestone, 1.0) if next_milestone > 0 else 1.0

    st.markdown(f"**Milestone Progress:** {total} athletes — next goal: {next_milestone}")
    st.progress(progress)
    badges = " ".join(f"✅ {m}" if total >= m else f"⬜ {m}" for m in milestones)
    st.caption(badges)

st.divider()

# Live Feed (auto-refresh every 3 seconds)
@st.fragment(run_every=timedelta(seconds=3))
def live_feed_section():
    rc = st.session_state.room_code
    athletes = get_athletes(rc)
    recent = athletes[:10]  # already sorted desc by added_at

    if recent:
        st.markdown("**Live Feed**")
        for a in recent:
            name = a.get("matched_name") or a.get("name", "?")
            sport = a.get("sport", "?")
            country = a.get("country") or "?"
            added_by = a.get("added_by", "?")
            time_ago = _format_relative_time(a.get("added_at", ""))
            st.markdown(
                f"**{added_by}** added **{name}** · {sport} · {country} · {time_ago}"
            )

live_feed_section()

st.divider()

# Stats Section (manual refresh via button)
@st.fragment
def stats_section():
    col_h1, col_h2 = st.columns([6, 1])
    with col_h1:
        st.header("Statistics")
    with col_h2:
        st.write("")
        st.button("🔄", key="refresh_stats", help="Refresh statistics")

    rc = st.session_state.room_code
    pn = st.session_state.player_name

    # Single Firebase read — compute all stats locally
    all_athletes = get_athletes(rc)
    stats: dict[str, int] = {}
    country_stats: dict[str, int] = {}
    player_stats: dict[str, int] = {}
    for a in all_athletes:
        s = a.get("sport", "Unknown")
        c = a.get("country") or "Unknown"
        p = a.get("added_by", "Unknown")
        stats[s] = stats.get(s, 0) + 1
        country_stats[c] = country_stats.get(c, 0) + 1
        player_stats[p] = player_stats.get(p, 0) + 1

    if stats:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["By Sport", "By Country", "Leaderboard", "Collection", "Achievements"])

        with tab1:
            sorted_sports = sorted(stats.items(), key=lambda x: -x[1])[:6]
            if sorted_sports:
                cols = st.columns(len(sorted_sports))
                for i, (sport, count) in enumerate(sorted_sports):
                    cols[i].metric(sport, count)

            df = pd.DataFrame({"Sport": stats.keys(), "Count": stats.values()})
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X("Sport:N", sort="-y"),
                y=alt.Y("Count:Q"),
                color=alt.Color("Sport:N", legend=None)
            ).properties(height=300)
            text = chart.mark_text(dy=-10, fontSize=16, fontWeight="bold").encode(text="Count:Q")
            st.altair_chart(chart + text, use_container_width=True)

        with tab2:
            sorted_countries = sorted(country_stats.items(), key=lambda x: -x[1])[:6]
            if sorted_countries:
                cols = st.columns(len(sorted_countries))
                for i, (country, count) in enumerate(sorted_countries):
                    cols[i].metric(country, count)

            df = pd.DataFrame({"Country": country_stats.keys(), "Count": country_stats.values()})
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X("Country:N", sort="-y"),
                y=alt.Y("Count:Q"),
                color=alt.Color("Country:N", legend=None)
            ).properties(height=300)
            text = chart.mark_text(dy=-10, fontSize=16, fontWeight="bold").encode(text="Count:Q")
            st.altair_chart(chart + text, use_container_width=True)

        with tab3:
            st.subheader("🏆 Leaderboard")
            player_scores = get_player_scores(rc)
            sorted_by_pts = sorted(player_scores.items(), key=lambda x: -x[1]["total_pts"])

            for i, (pname, sc) in enumerate(sorted_by_pts):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                is_me = " (You)" if pname == pn else ""
                st.markdown(
                    f"### {medal} {pname}{is_me} — {sc['total_pts']} pts "
                    f"({sc['count']} athletes, avg {sc['avg']})"
                )

        with tab4:
            st.subheader("📦 Collection")

            # Sport coverage
            all_supported = get_supported_sports()[:-1]  # exclude the "... and more" entry
            found_sports = set(stats.keys())
            missing_sports = [s for s in all_supported if s not in found_sports]

            st.markdown(f"**Sports Found:** {len(found_sports)} / {len(all_supported)}")
            st.progress(min(len(found_sports) / len(all_supported), 1.0))

            found_tags = " ".join(f":green-background[{s}]" for s in sorted(found_sports))
            if found_tags:
                st.markdown(found_tags)

            if missing_sports:
                st.caption("Missing: " + " ".join(f":gray-background[{s}]" for s in missing_sports[:12]))

            st.divider()

            # Country coverage
            found_countries = set(country_stats.keys()) - {"Unknown"}
            country_target = get_total_countries() or 1
            st.markdown(f"**Countries Found:** {len(found_countries)} / {country_target}")
            st.progress(min(len(found_countries) / country_target, 1.0))
            if found_countries:
                st.caption(", ".join(sorted(found_countries)))

        with tab5:
            st.subheader("🏆 Achievements")

            total_a = sum(stats.values())
            n_sports = len(stats)
            n_countries = len(set(country_stats.keys()) - {"Unknown"})
            n_players = len(player_stats)

            # Check best streak across all players
            room_data = get_room_data(rc)
            players_data = room_data.get("players", {})
            max_best_streak = max((p.get("best_streak", 0) for p in players_data.values()), default=0)

            # Check for athletes from defunct/historical countries
            _defunct_countries = {
                "Ottoman Empire", "Soviet Union", "USSR", "Yugoslavia",
                "Czechoslovakia", "East Germany", "West Germany", "Prussia",
                "Austria-Hungary", "British Raj", "Mandatory Palestine",
                "Rhodesia", "Zaire", "Burma", "Siam", "Persia", "Ceylon",
                "Dutch East Indies", "Serbia and Montenegro", "Korean Empire",
                "German Empire", "Russian Empire", "Qing dynasty", "British Empire",
                "Austrian Empire", "Holy Roman Empire", "Empire of Japan",
                "Chinese Empire", "Bohemia", "Papal States", "Republic of Venice",
                "Republic of Vietnam", "German Confederation",
                "Kingdom of Italy", "Kingdom of Yugoslavia",
                "Kingdom of Hungary", "Kingdom of Romania", "Kingdom of Greece",
                "Kingdom of Egypt", "Kingdom of Serbia", "Kingdom of Bulgaria",
                "Kingdom of Poland", "Kingdom of Prussia", "Kingdom of Saxony",
                "Kingdom of England", "Kingdom of Scotland", "Kingdom of Ireland",
                "Kingdom of France", "Kingdom of Great Britain", "Kingdom of Castile",
                "Kingdom of Naples", "Kingdom of Sicily", "Kingdom of Bohemia",
                "Kingdom of Mysore", "Kingdom of Portugal", "Kingdom of W\u00fcrttemberg",
                "Socialist Federal Republic of Yugoslavia",
                "Byelorussian Soviet Socialist Republic",
                "Russian Soviet Federative Socialist Republic",
                "Ukrainian Soviet Socialist Republic",
                "United Kingdom of Great Britain and Ireland",
                "United Kingdom of the Netherlands",
                "Grand Duchy of Finland", "Grand Duchy of Baden",
                "Grand Duchy of Hesse", "Grand Duchy of Tuscany",
                "Grand Duchy of Mecklenburg-Strelitz",
                "Duchy of Brabant", "Duchy of Brunswick", "Duchy of Urbino",
                "Republic of Egypt", "Republic of China",
            }
            room_athletes = list(room_data.get("athletes", {}).values())
            defunct_count = len({a.get("country") for a in room_athletes if a.get("country") in _defunct_countries})

            achievements = [
                ("First Steps", "👶", total_a >= 1, "Add 1 athlete"),
                ("Getting Started", "🌱", total_a >= 10, "Add 10 athletes"),
                ("Half Century", "⭐", total_a >= 50, "Add 50 athletes"),
                ("Century Club", "💯", total_a >= 100, "Add 100 athletes"),
                ("Sport Explorer", "🔍", n_sports >= 5, "Find 5 different sports"),
                ("Sport Master", "🏅", n_sports >= 10, "Find 10 different sports"),
                ("Globe Trotter", "🌍", n_countries >= 10, "Find 10 different countries"),
                ("World Tour", "✈️", n_countries >= 25, "Find 25 different countries"),
                ("Team Effort", "🤝", n_players >= 3, "3+ players contribute"),
                ("Streak Legend", "🔥", max_best_streak >= 10, "Any player gets a 10 best streak"),
                ("Grandpa", "👴", defunct_count >= 1, "Add athlete from a defunct country"),
                ("Historian", "📜", defunct_count >= 5, "5 athletes from defunct countries"),
            ]

            unlocked = sum(1 for *_, u, _ in achievements if u)
            st.markdown(f"**{unlocked} / {len(achievements)}** unlocked")

            cols = st.columns(6)
            for i, (name, icon, is_unlocked, hint) in enumerate(achievements):
                with cols[i % 6]:
                    if is_unlocked:
                        st.markdown(
                            f"<div style='text-align:center;padding:12px 8px;border-radius:10px;"
                            f"border:2px solid rgba(76,175,80,0.5);"
                            f"background:rgba(76,175,80,0.12);margin-bottom:8px'>"
                            f"<div style='font-size:2em'>{icon}</div>"
                            f"<div style='font-size:0.85em;font-weight:600;margin-top:4px'>{name}</div></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<div style='text-align:center;padding:12px 8px;border-radius:10px;"
                            f"border:2px solid rgba(255,255,255,0.08);"
                            f"background:rgba(255,255,255,0.04);margin-bottom:8px'>"
                            f"<div style='font-size:2em;opacity:0.3'>🔒</div>"
                            f"<div style='font-size:0.85em;font-weight:600;margin-top:4px;opacity:0.4'>{name}</div>"
                            f"<div style='font-size:0.7em;opacity:0.3;margin-top:2px'>{hint}</div></div>",
                            unsafe_allow_html=True
                        )

    else:
        st.info("No athletes added yet. Start adding athletes to see statistics!")

stats_section()

# Athletes Table Section (live auto-refresh every 5 seconds)
@st.fragment(run_every=timedelta(seconds=5))
def athletes_section():
    rc = st.session_state.room_code

    st.header("All Athletes")

    athletes = get_athletes(rc)

    if athletes:
        table_data = []
        for i, a in enumerate(athletes):
            pts, _, _ = calculate_athlete_points(a.get("sport", ""), a.get("country"), athletes)
            ch_bonus = a.get("challenge_bonus", 0)
            table_data.append({
                "#": len(athletes) - i,
                "Name": a.get("matched_name") or a["name"],
                "Sport": a["sport"],
                "Country": a.get("country") or "—",
                "Points": pts + ch_bonus,
                "Added By": a.get("added_by", "—"),
            })
        df = pd.DataFrame(table_data)
        df = df.sort_values("#", ascending=False).reset_index(drop=True)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "#": st.column_config.NumberColumn(width="small"),
                "Name": st.column_config.TextColumn(width="medium"),
                "Sport": st.column_config.TextColumn(width="medium"),
                "Country": st.column_config.TextColumn(width="medium"),
                "Points": st.column_config.NumberColumn(width="small"),
                "Added By": st.column_config.TextColumn(width="medium"),
            },
        )

        st.caption(f"Total: {len(athletes)} athletes")

        st.divider()
        with st.expander("⚠️ Danger Zone"):
            if st.button("Clear All Room Data", type="secondary"):
                clear_room(rc)
                st.session_state.last_result = None
                st.rerun()
    else:
        st.info("No athletes in this room yet. Be the first to add one!")

athletes_section()

st.caption("💡 Athletes table auto-refreshes every 5 seconds")
