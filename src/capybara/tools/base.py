from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

class ToolPermission(Enum):
    ALWAYS = "always"   # Auto-approve
    ASK = "ask"         # Prompt user
    NEVER = "never"     # Block

class ToolSecurityConfig(BaseModel):
    permission: ToolPermission = ToolPermission.ASK
    allowlist: List[str] = []  # Auto-approve patterns (regex)
    denylist: List[str] = []   # Block patterns (regex)
