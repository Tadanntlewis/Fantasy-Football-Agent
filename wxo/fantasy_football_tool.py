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
def get_available_players(draft_id: str, position: str, limit: int = 20) -> str:
    """
    Get top available (undrafted) fantasy football players for a given position.
    Automatically checks the current draft picks and removes already-drafted players.
    Always use this tool instead of get_player_rankings when making draft recommendations.

    Args:
        draft_id: The Sleeper draft ID to check current picks against.
        position: Player position to filter by. One of: QB, RB, WR, TE, K, DEF.
        limit: Number of top available players to return. Defaults to 20, max 50.

    Returns:
        JSON string with top undrafted players sorted by rank, including name, team, position, age.
    """
    try:
        # Fetch draft picks and all players in parallel (sequential here for simplicity)
        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
        players = _get("https://api.sleeper.app/v1/players/nfl")

        pos = position.strip().upper()
        limit = min(int(limit), 50)

        # Build set of already-drafted player IDs
        drafted_ids = set()
        for pick in picks:
            pid = pick.get("player_id")
            if pid:
                drafted_ids.add(str(pid))

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
def get_position_tiers(draft_id: str, position: str) -> str:
    """
    Get live fantasy football player tiers for a position, with already-drafted players removed.
    Tiers are calculated dynamically from Sleeper rankings using rank gaps.
    Use this tool when making draft recommendations to understand tier breaks.

    Args:
        draft_id: The Sleeper draft ID — used to exclude already-drafted players.
        position: Player position. One of: QB, RB, WR, TE, K, DEF.

    Returns:
        Plain text tier breakdown showing available players grouped by tier,
        with name, team, age and rank for each player.
    """
    try:
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

