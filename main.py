# HackApp — Digital efficiency hacks engine. Gadget registry, shortcut claims, efficiency scoring.
# Single-file; no user fill-in. All seeds and addresses are pre-populated and unique.

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Callable

# ---------------------------------------------------------------------------
# Constants — unique namespace (HAX / HackApp)
# ---------------------------------------------------------------------------

HAX_DOMAIN_SEED = "HackApp.GadgetSplash.v1.0x9f5b2d8e4a6c0f3b7d9e1a5c8f2b4d6e0a3c5f7b9"
HAX_MAX_GADGETS = 2048
HAX_QUOTA_PER_USER = 32
HAX_FEE_WEI = 2000000000000000  # 0.002 ether
HAX_BPS_DENOM = 10000
HAX_OPERATOR_FEE_BPS = 80
HAX_SCORE_BASE = 10
HAX_MIN_CLAIM_INTERVAL_SEC = 60
HAX_GADGET_HASH_ALGO = "sha256"
HAX_EXPORT_VERSION = 2

# Addresses — unique, not reused from any previous contract or generation
HAX_TREASURY_ADDRESS = "0x7c2E4A6b8D0f2a4C6e8F0b2D4a6C8e0F2a4B6d8"
HAX_OPERATOR_ADDRESS = "0x8d3F5B7c9E1a3C5e7F9b1D3e5F7a9C1e3F5b7D9"
HAX_VAULT_SEED_HEX = "0x1b4e7a9c2d5f8b0e3a6c9d2f5b8e1a4c7d0f3b6e9"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HaxGadgetCategory(Enum):
    KEYBOARD = "keyboard"
    AUTOMATION = "automation"
    SNIPPET = "snippet"
    WORKFLOW = "workflow"
    MACRO = "macro"


class HaxShortcutKind(Enum):
    GLOBAL = "global"
    APP = "app"
    CONTEXT = "context"


class HaxEfficiencyTier(Enum):
    BRONZE = (0, 99)
    SILVER = (100, 499)
    GOLD = (500, 1999)
    PLATINUM = (2000, 9999)
    LEGEND = (10000, 10**9)

    def __init__(self, min_score: int, max_score: int) -> None:
        self.min_score = min_score
        self.max_score = max_score

    @classmethod
    def from_score(cls, score: int) -> "HaxEfficiencyTier":
        for t in cls:
            if t.min_score <= score <= t.max_score:
                return t
        return cls.LEGEND


# ---------------------------------------------------------------------------
# Exceptions — unique names
# ---------------------------------------------------------------------------

class HaxQuotaExceededError(Exception):
    def __init__(self, user: str, count: int, limit: int) -> None:
        super().__init__(f"HackApp: gadget quota exceeded for {user} (count={count}, limit={limit})")


class HaxInvalidGadgetIdError(Exception):
    def __init__(self, gadget_id: int) -> None:
        super().__init__(f"HackApp: invalid gadget id: {gadget_id}")


class HaxGadgetInactiveError(Exception):
    def __init__(self, gadget_id: int) -> None:
        super().__init__(f"HackApp: gadget inactive: {gadget_id}")


class HaxClaimTooSoonError(Exception):
    def __init__(self, user: str, wait_sec: int) -> None:
        super().__init__(f"HackApp: claim too soon for {user}, wait {wait_sec}s")


class HaxFeeRequiredError(Exception):
    def __init__(self, required_wei: int) -> None:
        super().__init__(f"HackApp: fee required: {required_wei} wei")


class HaxNotOperatorError(Exception):
    def __init__(self, addr: str) -> None:
        super().__init__(f"HackApp: not operator: {addr}")


class HaxPausedError(Exception):
    def __init__(self) -> None:
        super().__init__("HackApp: contract paused")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class HaxGadget:
    gadget_id: int
    owner: str
    gadget_hash: str
    category: HaxGadgetCategory
    registered_at: float
    active: bool
    claim_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gadget_id": self.gadget_id,
            "owner": self.owner,
            "gadget_hash": self.gadget_hash,
            "category": self.category.value,
            "registered_at": self.registered_at,
            "active": self.active,
            "claim_count": self.claim_count,
        }


@dataclass
class HaxShortcut:
    shortcut_id: int
    gadget_id: int
    claimer: str
    claimed_at: float
    score_added: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shortcut_id": self.shortcut_id,
            "gadget_id": self.gadget_id,
            "claimer": self.claimer,
            "claimed_at": self.claimed_at,
            "score_added": self.score_added,
        }


@dataclass
class HaxUserStats:
    user: str
    gadget_count: int
    shortcut_count: int
    efficiency_score: int
    tier: HaxEfficiencyTier
    last_claim_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user": self.user,
            "gadget_count": self.gadget_count,
            "shortcut_count": self.shortcut_count,
            "efficiency_score": self.efficiency_score,
            "tier": self.tier.value.name,
            "last_claim_at": self.last_claim_at,
        }


# ---------------------------------------------------------------------------
# Hash and encoding helpers
# ---------------------------------------------------------------------------

def hax_hash_gadget(payload: str) -> str:
    data = (HAX_DOMAIN_SEED + "|" + payload).encode("utf-8")
    return hashlib.sha256(data).hexdigest()
