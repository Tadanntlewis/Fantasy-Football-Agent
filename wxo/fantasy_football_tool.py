"""
Fantasy Football tools for watsonx Orchestrate.
Each @tool-decorated function is exposed as a usable tool in the agent.
"""

import json
import os
import sys
from pathlib import Path

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.sleeper_client import SleeperClient
from core.rankings_manager import RankingsManager


@tool(permission=ToolPermission.READ_ONLY)
def get_player_rankings(position: str, scoring: str = "half_ppr", limit: int = 20) -> str:
    """
    Get fantasy football player rankings for a given position.

    Args:
        position: Player position to rank. One of: QB, RB, WR, TE, K, FLX, OP, ALL.
        scoring: Scoring format. One of: ppr, half_ppr, standard. Defaults to half_ppr.
        limit: Number of players to return. Defaults to 20.

    Returns:
        JSON string containing ranked players with name, team, position, and rank.
    """
    try:
        manager = RankingsManager()
        players = manager.get_rankings(position=position.upper(), scoring_format=scoring, limit=limit)
        return json.dumps(players, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool(permission=ToolPermission.READ_ONLY)
def get_league_info(league_id: str) -> str:
    """
    Get details about a Sleeper fantasy football league.

    Args:
        league_id: The Sleeper league ID to look up.

    Returns:
        JSON string with league name, scoring settings, roster positions, and team count.
    """
    try:
        client = SleeperClient()
        league = client.get_league(league_id)
        return json.dumps(league, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool(permission=ToolPermission.READ_ONLY)
def get_draft_recommendations(
    league_id: str,
    draft_pick: int,
    already_drafted: str = "",
    scoring: str = "half_ppr",
) -> str:
    """
    Get AI-powered draft pick recommendations for a fantasy football draft.

    Args:
        league_id: The Sleeper league ID.
        draft_pick: Current draft pick number (overall pick, e.g. 5 for 5th overall).
        already_drafted: Comma-separated list of player names already drafted by your team.
        scoring: Scoring format. One of: ppr, half_ppr, standard. Defaults to half_ppr.

    Returns:
        JSON string with recommended players and reasoning for the current pick.
    """
    try:
        client = SleeperClient()
        manager = RankingsManager()

        drafted = [p.strip() for p in already_drafted.split(",") if p.strip()]
        league = client.get_league(league_id)
        roster_positions = league.get("roster_positions", [])

        # Determine positional need based on already drafted players
        position_counts = {}
        for p in drafted:
            # Simple heuristic — real logic lives in RankingsManager
            pass

        recommendations = manager.get_draft_recommendations(
            pick_number=draft_pick,
            drafted_players=drafted,
            roster_positions=roster_positions,
            scoring_format=scoring,
        )
        return json.dumps(recommendations, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool(permission=ToolPermission.READ_ONLY)
def compare_players(player_names: str, scoring: str = "half_ppr") -> str:
    """
    Compare two or more fantasy football players side by side.

    Args:
        player_names: Comma-separated list of player names to compare (e.g. "CeeDee Lamb, Ja'Marr Chase").
        scoring: Scoring format. One of: ppr, half_ppr, standard. Defaults to half_ppr.

    Returns:
        JSON string with a comparison of each player's rankings, projected points, and recommendation.
    """
    try:
        manager = RankingsManager()
        names = [n.strip() for n in player_names.split(",") if n.strip()]
        comparison = manager.compare_players(player_names=names, scoring_format=scoring)
        return json.dumps(comparison, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
