"""
Fantasy Football tools for watsonx Orchestrate.
Uses only Python standard library (urllib) for HTTP — no external dependencies.
"""

import json
import urllib.request
import ssl
from ibm_watsonx_orchestrate.agent_builder.tools import tool


def _get(url: str):
    """Make a GET request using stdlib urllib, returning parsed JSON."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "FantasyFootballAgent/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


@tool
def get_league_info(league_id: str) -> str:
    """
    Get details about a Sleeper fantasy football league.

    Args:
        league_id: The Sleeper league ID to look up (e.g. "1048347876222349312").

    Returns:
        JSON string with league name, scoring settings, roster positions, and team count.
    """
    try:
        data = _get(f"https://api.sleeper.app/v1/league/{league_id}")
        result = {
            "name": str(data.get("name") or ""),
            "total_rosters": int(data["total_rosters"]) if data.get("total_rosters") is not None else None,
            "status": str(data.get("status") or ""),
            "season": str(data.get("season") or ""),
            "draft_id": str(data.get("draft_id") or ""),
            "roster_positions": [str(p) for p in data.get("roster_positions") or []],
            "scoring_settings": {
                k: float(v) for k, v in (data.get("scoring_settings") or {}).items()
                if k in ("rec", "pass_td", "rush_td", "bonus_rec_te")
            },
        }
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_player_rankings(position: str, scoring: str = "half_ppr", limit: int = 20) -> str:
    """
    Get top fantasy football players by position from Sleeper's database.

    Args:
        position: Player position to filter by. One of: QB, RB, WR, TE, K, DEF.
        scoring: Scoring format (for reference only): ppr, half_ppr, standard.
        limit: Number of top players to return. Defaults to 20, max 50.

    Returns:
        JSON string with top players sorted by rank including name, team, position, age.
    """
    try:
        players = _get("https://api.sleeper.app/v1/players/nfl")
        pos = position.strip().upper()
        limit = min(int(limit), 50)

        filtered = []
        for pid, p in players.items():
            if not p.get("active") or not p.get("team"):
                continue
            positions = p.get("fantasy_positions") or []
            if pos not in positions:
                continue
            rank = p.get("search_rank")
            if rank is None or int(rank) >= 999:
                continue
            filtered.append({
                "rank": int(rank),
                "name": (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip(),
                "team": str(p.get("team") or ""),
                "position": pos,
                "age": int(p["age"]) if p.get("age") is not None else None,
                "years_exp": int(p["years_exp"]) if p.get("years_exp") is not None else None,
                "injury_status": str(p["injury_status"]) if p.get("injury_status") else None,
            })

        filtered.sort(key=lambda x: x["rank"])
        return json.dumps(filtered[:limit])
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_draft_picks(draft_id: str) -> str:
    """
    Get all picks made so far in a Sleeper fantasy football draft.

    Args:
        draft_id: The Sleeper draft ID (found via get_league_info as draft_id field).

    Returns:
        JSON string with each pick including round, pick number, player name, team, and position.
    """
    try:
        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
        result = [
            {
                "round": int(pick["round"]) if pick.get("round") is not None else None,
                "pick_no": int(pick["pick_no"]) if pick.get("pick_no") is not None else None,
                "player_id": str(pick.get("player_id") or ""),
                "name": (str((pick.get("metadata") or {}).get("first_name") or "") + " " + str((pick.get("metadata") or {}).get("last_name") or "")).strip(),
                "position": str((pick.get("metadata") or {}).get("position") or ""),
                "team": str((pick.get("metadata") or {}).get("team") or ""),
            }
            for pick in picks
        ]
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_available_players(draft_id: str, position: str, current_pick: int = 0, limit: int = 20) -> str:
    """
    Get top available (undrafted) fantasy football players for a given position.
    Automatically checks the current draft picks and removes already-drafted players.
    Always use this tool instead of get_player_rankings when making draft recommendations.

    Args:
        draft_id: The Sleeper draft ID to check current picks against.
        position: Player position to filter by. One of: QB, RB, WR, TE, K, DEF.
        current_pick: The current overall pick number in the draft (e.g. 9 for pick 9).
                      Used to enforce round-based restrictions. Pass 0 if unknown.
        limit: Number of top available players to return. Defaults to 20, max 50.

    Returns:
        JSON string with top undrafted players sorted by rank, including name, team, position, age.
    """
    try:
        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
        pos = position.strip().upper()
        limit = min(int(limit), 50)

        # PuntOff slot map: overall pick → round (10-team half-PPR snake, draft slot 9)
        SLOT_MAP = {
            9: 1, 12: 2, 29: 3, 32: 4, 49: 5, 52: 6, 69: 7, 72: 8,
            89: 9, 92: 10, 109: 11, 112: 12, 129: 13, 132: 14, 149: 15, 152: 16, 169: 17
        }
        # Derive round from slot map; fall back to formula only if pick not in map
        cp = int(current_pick)
        if cp > 0:
            current_round = SLOT_MAP.get(cp, ((cp - 1) // 10) + 1)
        else:
            current_round = 0

        # Hard enforcement: K and DEF are banned before Round 16
        if pos in ("K", "DEF") and current_round > 0 and current_round < 16:
            return json.dumps({
                "blocked": True,
                "reason": f"K and DEF cannot be drafted before Round 16. Current round is {current_round} (overall pick {cp}). Do not suggest K or DEF — recommend RB, WR, QB, or TE instead."
            })

        # Hard enforcement: QB is banned before Round 6
        if pos == "QB" and current_round > 0 and current_round < 6:
            return json.dumps({
                "blocked": True,
                "reason": f"QB cannot be drafted before Round 6. Current round is {current_round} (overall pick {cp}). Do not suggest QB — recommend RB, WR, or TE instead."
            })

        # Build set of already-drafted player IDs
        drafted_ids = {str(pick.get("player_id")) for pick in picks if pick.get("player_id")}

        # DEF: Sleeper has no search_rank for defenses — use curated ranking
        if pos == "DEF":
            def_rankings = [
                "SF", "BAL", "BUF", "DET", "GB", "PHI", "KC", "MIN",
                "HOU", "CLE", "PIT", "DAL", "MIA", "NYJ", "LAC", "SEA",
                "TB", "DEN", "IND", "NE", "LV", "ARI", "ATL", "CIN",
                "LAR", "NYG", "CAR", "CHI", "TEN", "JAX", "WAS", "NO",
            ]
            available = [
                {"rank": i + 1, "name": f"{team} Defense", "team": team, "position": "DEF"}
                for i, team in enumerate(def_rankings)
                if team not in drafted_ids
            ]
            return json.dumps(available[:limit])

        players = _get("https://api.sleeper.app/v1/players/nfl")

        # Filter to available players at the requested position
        available = []
        for pid, p in players.items():
            if str(pid) in drafted_ids:
                continue
            if not p.get("active") or not p.get("team"):
                continue
            positions = p.get("fantasy_positions") or []
            if pos not in positions:
                continue
            rank = p.get("search_rank")
            if rank is None or int(rank) >= 999:
                continue
            available.append({
                "rank": int(rank),
                "name": (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip(),
                "team": str(p.get("team") or ""),
                "position": pos,
                "age": int(p["age"]) if p.get("age") is not None else None,
                "years_exp": int(p["years_exp"]) if p.get("years_exp") is not None else None,
                "injury_status": str(p["injury_status"]) if p.get("injury_status") else None,
            })

        available.sort(key=lambda x: x["rank"])
        return json.dumps(available[:limit])
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_all_drafted_players(draft_id: str, round_number: int = 0) -> str:
    """
    Get ALL players drafted so far in a Sleeper draft, optionally filtered by round.
    Use round_number=0 to get all picks. Use round_number=1 for round 1 only, etc.
    To get all 170 picks call this once with round_number=0.

    Args:
        draft_id: The Sleeper draft ID.
        round_number: Round to filter by (0 = all rounds, 1-17 = specific round).

    Returns:
        Plain text list of every drafted player grouped by round with name, position, team.
    """
    try:
        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")

        # Group by round
        rounds = {}
        for pick in picks:
            r = int(pick.get("round") or 0)
            if round_number != 0 and r != round_number:
                continue
            m = pick.get("metadata") or {}
            name = (str(m.get("first_name") or "") + " " + str(m.get("last_name") or "")).strip()
            pos = str(m.get("position") or "")
            team = str(m.get("team") or "")
            slot = int(pick.get("draft_slot") or pick.get("pick_no") or 0)
            if r not in rounds:
                rounds[r] = []
            rounds[r].append(f"  {slot}. {name} ({pos}, {team})")

        if not rounds:
            return f"No picks found for round {round_number}."

        lines = [f"Total picks: {sum(len(v) for v in rounds.values())}"]
        for r in sorted(rounds.keys()):
            lines.append(f"Round {r}:")
            lines.extend(rounds[r])

        return "\n".join(lines)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_position_tiers(draft_id: str, position: str, current_pick: int = 0) -> str:
    """
    Get live fantasy football player tiers for a position, with already-drafted players removed.
    Tiers are calculated dynamically from Sleeper rankings using rank gaps.
    Use this tool when making draft recommendations to understand tier breaks.

    Args:
        draft_id: The Sleeper draft ID — used to exclude already-drafted players.
        position: Player position. One of: QB, RB, WR, TE, K, DEF.
        current_pick: The current overall pick number in the draft (e.g. 9 for pick 9).
                      Used to enforce round-based restrictions. Pass 0 if unknown.

    Returns:
        Plain text tier breakdown showing available players grouped by tier,
        with name, team, age and rank for each player.
    """
    try:
        # PuntOff slot map: overall pick → round (10-team half-PPR snake, draft slot 9)
        SLOT_MAP = {
            9: 1, 12: 2, 29: 3, 32: 4, 49: 5, 52: 6, 69: 7, 72: 8,
            89: 9, 92: 10, 109: 11, 112: 12, 129: 13, 132: 14, 149: 15, 152: 16, 169: 17
        }
        cp = int(current_pick)
        current_round = SLOT_MAP.get(cp, ((cp - 1) // 10) + 1) if cp > 0 else 0

        # Hard enforcement: K and DEF are banned before Round 16
        if position.strip().upper() in ("K", "DEF") and current_round > 0 and current_round < 16:
            return f"BLOCKED: K and DEF cannot be drafted before Round 16. Current round is {current_round} (overall pick {cp}). Do not suggest K or DEF — recommend RB, WR, QB, or TE instead."

        # Hard enforcement: QB is banned before Round 6
        if position.strip().upper() == "QB" and current_round > 0 and current_round < 6:
            return f"BLOCKED: QB cannot be drafted before Round 6. Current round is {current_round} (overall pick {cp}). Do not suggest QB — recommend RB, WR, or TE instead."

        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
        players = _get("https://api.sleeper.app/v1/players/nfl")

        pos = position.strip().upper()

        # Build set of drafted player IDs
        drafted_ids = {str(pick.get("player_id")) for pick in picks if pick.get("player_id")}

        # DEF: Sleeper doesn't rank defenses — use a curated tier list and filter drafted ones
        if pos == "DEF":
            # Pre-ranked defenses by 2025 fantasy performance and 2026 outlook
            def_rankings = [
                "SF", "BAL", "BUF", "DET", "GB", "PHI", "KC", "MIN",
                "HOU", "CLE", "PIT", "DAL", "MIA", "NYJ", "LAC", "SEA",
                "TB", "DEN", "IND", "NE", "LV", "ARI", "ATL", "CIN",
                "LAR", "NYG", "CAR", "CHI", "TEN", "JAX", "WAS", "NO",
            ]
            lines = ["Available DEF Tiers (live, undrafted only):"]
            tier_breaks = [3, 7, 12, 18]  # tier boundaries by index
            current_tier = 1
            count = 0
            lines.append(f"\nTier 1:")
            for team in def_rankings:
                # DEF player_id in Sleeper is the team abbreviation
                if team in drafted_ids:
                    continue
                if count in tier_breaks:
                    current_tier += 1
                    lines.append(f"\nTier {current_tier}:")
                lines.append(f"  {team} Defense")
                count += 1
            lines.append(f"\nTotal available DEF: {count}")
            return "\n".join(lines)

        # Collect available players at position
        available = []
        for pid, p in players.items():
            if str(pid) in drafted_ids:
                continue
            if not p.get("active") or not p.get("team"):
                continue
            positions = p.get("fantasy_positions") or []
            if pos not in positions:
                continue
            rank = p.get("search_rank")
            if rank is None or int(rank) >= 999:
                continue
            available.append({
                "rank": int(rank),
                "name": (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip(),
                "team": str(p.get("team") or ""),
                "age": int(p["age"]) if p.get("age") is not None else None,
                "years_exp": int(p["years_exp"]) if p.get("years_exp") is not None else None,
            })

        available.sort(key=lambda x: x["rank"])

        if not available:
            return f"No available {pos} players found."

        # Build tiers using rank gaps
        # A new tier starts when the gap to the next player exceeds a threshold
        tier_thresholds = {"QB": 8, "RB": 5, "WR": 5, "TE": 8, "K": 10, "DEF": 10}
        threshold = tier_thresholds.get(pos, 6)

        tiers = []
        current_tier = [available[0]]
        for i in range(1, len(available)):
            gap = available[i]["rank"] - available[i - 1]["rank"]
            if gap >= threshold:
                tiers.append(current_tier)
                current_tier = [available[i]]
            else:
                current_tier.append(available[i])
            # Cap at top 8 tiers to keep output concise
            if len(tiers) >= 8:
                break
        tiers.append(current_tier)

        # Format output
        lines = [f"Available {pos} Tiers (live, undrafted only):"]
        for i, tier in enumerate(tiers[:8], 1):
            lines.append(f"\nTier {i}:")
            for p in tier:
                age_str = f", age {p['age']}" if p.get("age") else ""
                lines.append(f"  {p['name']} ({p['team']}{age_str}) [rank {p['rank']}]")

        lines.append(f"\nTotal available {pos}: {len(available)}")
        return "\n".join(lines)

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_my_roster(draft_id: str) -> str:
    """
    Get PuntOff's current roster — all players drafted by PuntOff so far.
    Always call this before making a draft recommendation to know what positions are filled.

    Args:
        draft_id: The Sleeper draft ID.

    Returns:
        Plain text showing PuntOff's drafted players by position,
        current roster composition, and remaining needs.
    """
    try:
        PUNTOFF_USER_ID = "1393322190824284160"

        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")

        # Filter to PuntOff's picks only
        my_picks = [p for p in picks if str(p.get("picked_by") or "") == PUNTOFF_USER_ID]

        if not my_picks:
            return "PuntOff has not made any picks yet."

        # Build roster grouped by position
        roster = {}
        for pick in my_picks:
            m = pick.get("metadata") or {}
            name = (str(m.get("first_name") or "") + " " + str(m.get("last_name") or "")).strip()
            pos = str(m.get("position") or "?")
            team = str(m.get("team") or "")
            pick_no = int(pick.get("pick_no") or 0)
            round_no = int(pick.get("round") or 0)
            if pos not in roster:
                roster[pos] = []
            roster[pos].append(f"  Rd{round_no} Pk{pick_no}: {name} ({team})")

        # Starting lineup requirements from knowledge base
        lineup = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
        bench_spots = 8
        total_picks = 17

        lines = [f"PuntOff Roster ({len(my_picks)}/{total_picks} picks made):"]
        lines.append("")

        # Show players by position
        for pos in ["QB", "RB", "WR", "TE", "K", "DEF"]:
            players = roster.get(pos, [])
            needed = lineup.get(pos, 1)
            status = "✓" if len(players) >= needed else f"NEED {needed - len(players)}"
            lines.append(f"{pos} [{status}]:")
            if players:
                lines.extend(players)
            else:
                lines.append("  (none)")

        # Roster needs summary
        lines.append("")
        lines.append("Positional needs:")
        needs = []
        for pos, needed in lineup.items():
            count = len(roster.get(pos, []))
            if count < needed:
                needs.append(f"{pos} ({needed - count} more needed for starting lineup)")
        if needs:
            for n in needs:
                lines.append(f"  - {n}")
        else:
            lines.append("  Starting lineup positions filled. Focus on depth and upside.")

        picks_remaining = total_picks - len(my_picks)
        lines.append(f"\nPicks remaining: {picks_remaining}")

        return "\n".join(lines)

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_trending_players(trend_type: str = "add", limit: int = 15) -> str:
    """
    Get trending NFL players being added or dropped on Sleeper waiver wire.
    Players trending up (adds) signal positive news: injuries to starters, breakout performances,
    depth chart changes, or upcoming favorable matchups.
    Players trending down (drops) signal negative news: injuries, benching, or poor performance.

    Args:
        trend_type: Type of trend to fetch. Use "add" for players being added (positive news),
                    or "drop" for players being dropped (negative news). Defaults to "add".
        limit: Number of trending players to return. Defaults to 15, max 25.

    Returns:
        Plain text list of trending players with name, position, team, injury status,
        and add/drop count showing how much waiver activity they have seen in the last 24 hours.
    """
    try:
        limit = min(int(limit), 25)
        trend = "add" if trend_type.lower() != "drop" else "drop"

        # Fetch trending players (last 24 hours)
        trending = _get(
            f"https://api.sleeper.app/v1/players/nfl/trending/{trend}"
            f"?lookback_hours=24&limit={limit}"
        )

        if not trending:
            return f"No trending {trend} data available."

        # Fetch player details for names
        players = _get("https://api.sleeper.app/v1/players/nfl")

        lines = [f"Top {limit} trending {trend.upper()}S (last 24 hours):"]
        lines.append("")

        for i, item in enumerate(trending[:limit], 1):
            pid = str(item.get("player_id", ""))
            count = int(item.get("count", 0))
            p = players.get(pid, {})
            name = (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip()
            pos = str(p.get("position") or p.get("fantasy_positions", ["?"])[0] if p.get("fantasy_positions") else "?")
            team = str(p.get("team") or "FA")
            injury = str(p.get("injury_status") or "")
            injury_str = f" ⚠️ {injury}" if injury else ""
            lines.append(f"{i}. {name} ({pos}, {team}) — {count:,} {trend}s{injury_str}")

        lines.append("")
        lines.append("Note: High add counts = positive news (starter injury, depth chart rise, favourable matchup).")
        lines.append("Cross-reference with official team sources before acting on waiver trends.")

        return "\n".join(lines)

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_player_news(player_name: str) -> str:
    """
    Get current injury status and fantasy-relevant info for a specific NFL player from Sleeper.

    Args:
        player_name: Full or partial name of the player (e.g. "Christian McCaffrey", "McCaffrey").

    Returns:
        Plain text with the player's current injury status, depth chart position,
        team, position, age, and years of experience.
    """
    try:
        players = _get("https://api.sleeper.app/v1/players/nfl")

        name_lower = player_name.lower().strip()

        # Search by full name or partial match
        matches = []
        for pid, p in players.items():
            full = (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip().lower()
            search = str(p.get("search_full_name") or "").lower()
            if name_lower in full or name_lower in search:
                rank = p.get("search_rank") or 9999
                matches.append((rank, pid, p))

        if not matches:
            return f"No player found matching '{player_name}'. Try a different spelling."

        # Sort by rank and take best match
        matches.sort(key=lambda x: x[0])
        _, pid, p = matches[0]

        name = (str(p.get("first_name") or "") + " " + str(p.get("last_name") or "")).strip()
        pos = str(p.get("position") or "")
        team = str(p.get("team") or "Free Agent")
        injury_status = str(p.get("injury_status") or "None reported")
        injury_body = str(p.get("injury_body_part") or "")
        injury_notes = str(p.get("injury_notes") or "")
        depth_pos = str(p.get("depth_chart_position") or "")
        depth_order = p.get("depth_chart_order")
        age = p.get("age")
        years_exp = p.get("years_exp")
        status = str(p.get("status") or "")
        practice = str(p.get("practice_participation") or "")

        lines = [f"{name} — {pos}, {team}"]
        lines.append(f"Status: {status}")
        lines.append(f"Injury: {injury_status}" + (f" ({injury_body})" if injury_body else ""))
        if injury_notes:
            lines.append(f"Notes: {injury_notes}")
        if practice:
            lines.append(f"Practice: {practice}")
        if depth_pos and depth_order:
            lines.append(f"Depth chart: {depth_pos} #{depth_order}")
        lines.append(f"Age: {age} | Years exp: {years_exp}")

        return "\n".join(lines)

    except Exception as e:
        return json.dumps({"error": str(e)})

