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


