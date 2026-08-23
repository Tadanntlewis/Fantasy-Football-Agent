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
def get_all_drafted_players(draft_id: str) -> str:
    """
    Get a compact list of ALL players drafted so far in a Sleeper draft.
    Returns only the essential fields to avoid context limits.

    Args:
        draft_id: The Sleeper draft ID.

    Returns:
        JSON string with every drafted player: round, pick number, name, position, team.
    """
    try:
        picks = _get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
        lines = []
        for pick in picks:
            m = pick.get("metadata") or {}
            name = (str(m.get("first_name") or "") + " " + str(m.get("last_name") or "")).strip()
            pos = str(m.get("position") or "")
            team = str(m.get("team") or "")
            pick_no = pick.get("pick_no", "?")
            lines.append(f"{pick_no}. {name} ({pos}, {team})")
        total = len(lines)
        return f"Total drafted: {total}\n" + "\n".join(lines)
    except Exception as e:
        return json.dumps({"error": str(e)})

