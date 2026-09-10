"""
Orchestrator Agent Tool: Circular Commerce Evaluation.
"""

from typing import Optional, Dict, Any
from ..services.circular_commerce import evaluate_circular_actions
from ..auth import authenticate_user


def tool_evaluate_circular_action(
    user_id: str = "user0001",
    current_season: Optional[str] = None,
    days_unworn_threshold: int = 30,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates wardrobe items against seasonal weather windows and wearing frequency.
    Generates actionable circular commerce triggers:
    1. 'Style It Differently': In-season, unworn in N days, >= 2 potential unused combinations.
    2. 'Move to Storage': Out of current season window, but utilized during active season.
    3. 'Consider Donating': In-season, unworn across >= 2 seasons (> 180 days), low combinability.
    
    Args:
        user_id: Target user ID
        current_season: Optional season override ('Spring', 'Summer', 'Fall', 'Winter')
        days_unworn_threshold: Threshold in days for 'Style It Differently' flag (default 30)
        auth_token: Optional authentication token for user isolation
    """
    session = authenticate_user(auth_token or user_id)
    target_user_id = session.user_id

    return evaluate_circular_actions(
        user_id=target_user_id,
        current_season=current_season,
        days_unworn_threshold=days_unworn_threshold,
        auth_user_id=target_user_id
    )
