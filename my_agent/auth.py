"""
Authentication and User Scoping Service for naturallyEasy.
Ensures strict user data isolation across Firestore collections and BigQuery queries.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import hashlib
import time


@dataclass
class UserSession:
    user_id: str
    email: str
    display_name: str
    token: Optional[str] = None
    created_at: float = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


# In-memory mock session store for local dev / testing
_ACTIVE_SESSIONS: Dict[str, UserSession] = {}


def create_dev_session(user_id: str, email: str = None, display_name: str = None) -> UserSession:
    """
    Creates or registers a deterministic development session for a user.
    """
    clean_user_id = user_id.strip() if user_id else "user0001"
    email = email or f"{clean_user_id}@naturallyeasy.ai"
    display_name = display_name or f"User {clean_user_id}"
    token = f"token_{hashlib.sha256(clean_user_id.encode()).hexdigest()[:16]}"
    
    session = UserSession(
        user_id=clean_user_id,
        email=email,
        display_name=display_name,
        token=token
    )
    _ACTIVE_SESSIONS[token] = session
    return session


def authenticate_user(token_or_user_id: str) -> UserSession:
    """
    Authenticates a request and returns the validated UserSession.
    If a Bearer token or token prefix is passed, resolves session.
    If a plain user_id is passed, resolves or provisions a scoped session.
    """
    if not token_or_user_id:
        raise PermissionError("Authentication required: Missing user token or user_id.")
    
    clean_key = token_or_user_id.replace("Bearer ", "").strip()
    
    if clean_key in _ACTIVE_SESSIONS:
        return _ACTIVE_SESSIONS[clean_key]
    
    # Check if key is a user_id
    for session in _ACTIVE_SESSIONS.values():
        if session.user_id == clean_key:
            return session
            
    # Auto-provision scoped session for the given user_id
    return create_dev_session(user_id=clean_key)


def validate_user_access(request_user_id: str, target_user_id: str) -> bool:
    """
    Enforces strict access control: raises PermissionError if a user attempts
    to access or mutate data belonging to another user.
    """
    if not request_user_id or not target_user_id:
        raise PermissionError("Access Denied: Missing user identification.")
    
    if request_user_id != target_user_id:
        raise PermissionError(
            f"Access Denied: User '{request_user_id}' cannot access records belonging to '{target_user_id}'."
        )
    return True
