"""
Orchestrator Agent Tool: Predictive Wardrobe Gap Analysis.
"""

from typing import Optional, Dict, Any
from ..services.gap_analysis import analyze_wardrobe_gaps
from ..auth import authenticate_user


def tool_predictive_gap_analysis(
    user_id: str = "user0001",
    target_occasion: Optional[str] = None,
    expected_temp: Optional[float] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes combinatorial graph logic to identify isolated garments (<= 1 pairing),
    calculates Bridge Staples (connecting >= 3 underused items or fulfilling schedule needs),
    and returns gap recommendations across 3 categories:
    1. Versatility Multipliers
    2. Occasion Bridges
    3. Replacement Flags
    
    Args:
        user_id: Target user ID
        target_occasion: Optional schedule requirement (e.g. 'Formal / Black Tie', 'Work / Professional')
        expected_temp: Optional forecast temperature in Celsius (e.g. 16.0)
        auth_token: Optional authentication token for user isolation
    """
    session = authenticate_user(auth_token or user_id)
    target_user_id = session.user_id

    schedule = None
    if target_occasion:
        schedule = {
            "occasion": target_occasion,
            "expected_temp": expected_temp if expected_temp is not None else 20.0
        }

    return analyze_wardrobe_gaps(
        user_id=target_user_id,
        target_schedule=schedule,
        auth_user_id=target_user_id
    )
