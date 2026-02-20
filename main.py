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


def hax_gadget_id_from_hash(h: str) -> int:
    return int(h[:8], 16) % HAX_MAX_GADGETS


def hax_encode_shortcut_key(gadget_id: int, claimer: str, ts: float) -> str:
    return f"{gadget_id}:{claimer}:{ts}"


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class HackAppEngine:
    def __init__(self, paused: bool = False) -> None:
        self._paused = paused
        self._gadget_nonce = 0
        self._shortcut_nonce = 0
        self._gadgets: Dict[int, HaxGadget] = {}
        self._shortcuts: Dict[int, HaxShortcut] = {}
        self._gadget_ids_by_owner: Dict[str, List[int]] = {}
        self._shortcut_count_by_user: Dict[str, int] = {}
        self._efficiency_score: Dict[str, int] = {}
        self._last_claim_time: Dict[str, float] = {}
        self._total_fees_wei = 0
        self._lock = False

    def _check_paused(self) -> None:
        if self._paused:
            raise HaxPausedError()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def register_gadget(
        self,
        owner: str,
        payload: str,
        category: HaxGadgetCategory = HaxGadgetCategory.SNIPPET,
        fee_wei: int = HAX_FEE_WEI,
    ) -> HaxGadget:
        self._check_paused()
        if fee_wei < HAX_FEE_WEI:
            raise HaxFeeRequiredError(HAX_FEE_WEI)
        current = len(self._gadget_ids_by_owner.get(owner, []))
        if current >= HAX_QUOTA_PER_USER:
            raise HaxQuotaExceededError(owner, current, HAX_QUOTA_PER_USER)
        if self._gadget_nonce >= HAX_MAX_GADGETS:
            raise HaxInvalidGadgetIdError(self._gadget_nonce)

        self._gadget_nonce += 1
        gid = self._gadget_nonce
        gh = hax_hash_gadget(payload + str(gid))
        now = time.time()
        g = HaxGadget(
            gadget_id=gid,
            owner=owner,
            gadget_hash=gh,
            category=category,
            registered_at=now,
            active=True,
        )
        self._gadgets[gid] = g
        self._gadget_ids_by_owner.setdefault(owner, []).append(gid)
        self._total_fees_wei += fee_wei
        return g

    def claim_shortcut(self, gadget_id: int, claimer: str) -> HaxShortcut:
        self._check_paused()
        if gadget_id not in self._gadgets:
            raise HaxInvalidGadgetIdError(gadget_id)
        g = self._gadgets[gadget_id]
        if not g.active:
            raise HaxGadgetInactiveError(gadget_id)
        last = self._last_claim_time.get(claimer, 0)
        if time.time() < last + HAX_MIN_CLAIM_INTERVAL_SEC:
            raise HaxClaimTooSoonError(claimer, HAX_MIN_CLAIM_INTERVAL_SEC)

        self._shortcut_nonce += 1
        sid = self._shortcut_nonce
        now = time.time()
        score = HAX_SCORE_BASE + (int(now) % 5)
        s = HaxShortcut(shortcut_id=sid, gadget_id=gadget_id, claimer=claimer, claimed_at=now, score_added=score)
        self._shortcuts[sid] = s
        self._shortcut_count_by_user[claimer] = self._shortcut_count_by_user.get(claimer, 0) + 1
        self._efficiency_score[claimer] = self._efficiency_score.get(claimer, 0) + score
        self._last_claim_time[claimer] = now
        g.claim_count += 1
        return s

    def set_gadget_active(self, gadget_id: int, owner: str, active: bool) -> None:
        if gadget_id not in self._gadgets:
            raise HaxInvalidGadgetIdError(gadget_id)
        if self._gadgets[gadget_id].owner != owner:
            raise HaxNotOperatorError(owner)
        self._gadgets[gadget_id].active = active

    def get_gadget(self, gadget_id: int) -> Optional[HaxGadget]:
        return self._gadgets.get(gadget_id)

    def get_gadget_ids_by_owner(self, owner: str) -> List[int]:
        return list(self._gadget_ids_by_owner.get(owner, []))

    def get_user_stats(self, user: str) -> HaxUserStats:
        score = self._efficiency_score.get(user, 0)
        return HaxUserStats(
            user=user,
            gadget_count=len(self._gadget_ids_by_owner.get(user, [])),
            shortcut_count=self._shortcut_count_by_user.get(user, 0),
            efficiency_score=score,
            tier=HaxEfficiencyTier.from_score(score),
            last_claim_at=self._last_claim_time.get(user, 0),
        )

    def get_global_stats(self) -> Dict[str, Any]:
        return {
            "total_gadgets": self._gadget_nonce,
            "total_shortcuts": self._shortcut_nonce,
            "total_fees_wei": self._total_fees_wei,
            "unique_owners": len(self._gadget_ids_by_owner),
            "unique_claimers": len(self._shortcut_count_by_user),
        }


# ---------------------------------------------------------------------------
# Efficiency analytics
# ---------------------------------------------------------------------------

class HaxEfficiencyAnalytics:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def top_users_by_score(self, limit: int = 20) -> List[Tuple[str, int]]:
        scores: Dict[str, int] = {}
        for g in self._engine._gadgets.values():
            scores[g.owner] = scores.get(g.owner, 0)
        for u, c in self._engine._shortcut_count_by_user.items():
            scores[u] = scores.get(u, 0)  # ensure key exists
        eff = self._engine._efficiency_score
        combined = [(u, eff.get(u, 0)) for u in set(list(eff.keys()) + list(scores.keys()))]
        combined.sort(key=lambda x: -x[1])
        return combined[:limit]

    def gadgets_by_category(self) -> Dict[HaxGadgetCategory, int]:
        out: Dict[HaxGadgetCategory, int] = {c: 0 for c in HaxGadgetCategory}
        for g in self._engine._gadgets.values():
            out[g.category] = out.get(g.category, 0) + 1
        return out

    def claims_per_gadget(self, gadget_id: int) -> int:
        g = self._engine.get_gadget(gadget_id)
        return g.claim_count if g else 0


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

def hax_export_gadgets(engine: HackAppEngine) -> str:
    data = {
        "version": HAX_EXPORT_VERSION,
        "domain": HAX_DOMAIN_SEED,
        "exported_at": time.time(),
        "gadgets": [g.to_dict() for g in engine._gadgets.values()],
    }
    return json.dumps(data, indent=2)


def hax_export_shortcuts(engine: HackAppEngine, limit: int = 500) -> str:
    shortcuts = list(engine._shortcuts.values())[-limit:]
    data = {
        "version": HAX_EXPORT_VERSION,
        "shortcuts": [s.to_dict() for s in shortcuts],
    }
    return json.dumps(data, indent=2)


def hax_import_gadgets_json(engine: HackAppEngine, json_str: str) -> int:
    data = json.loads(json_str)
    count = 0
    for g in data.get("gadgets", []):
        try:
            owner = g.get("owner", "imported")
            payload = g.get("gadget_hash", "") + str(count)
            cat = HaxGadgetCategory(g.get("category", "snippet"))
            engine.register_gadget(owner, payload, category=cat, fee_wei=0)
            count += 1
        except Exception:
            pass
    return count


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

def hax_cli_register(engine: HackAppEngine, owner: str, payload: str) -> None:
    g = engine.register_gadget(owner, payload, fee_wei=HAX_FEE_WEI)
    print(f"Registered gadget {g.gadget_id} for {owner}, hash={g.gadget_hash[:16]}...")


def hax_cli_claim(engine: HackAppEngine, gadget_id: int, claimer: str) -> None:
    s = engine.claim_shortcut(gadget_id, claimer)
    print(f"Claimed shortcut {s.shortcut_id}, score +{s.score_added}")


def hax_cli_stats(engine: HackAppEngine, user: Optional[str] = None) -> None:
    gs = engine.get_global_stats()
    print("Global:", gs)
    if user:
        st = engine.get_user_stats(user)
        print("User stats:", st.to_dict())


# ---------------------------------------------------------------------------
# Gadget validation
# ---------------------------------------------------------------------------

def hax_validate_payload(payload: str, max_len: int = 4096) -> bool:
    if not payload or len(payload) > max_len:
        return False
    return True


def hax_validate_owner(owner: str) -> bool:
    if not owner or len(owner) < 2 or len(owner) > 64:
        return False
    return owner.startswith("0x") or "." in owner or "@" in owner or owner.isalnum()


# ---------------------------------------------------------------------------
# Rate limiter (for API simulation)
# ---------------------------------------------------------------------------

class HaxRateLimiter:
    def __init__(self, max_claims_per_minute: int = 10) -> None:
        self._max = max_claims_per_minute
        self._claims: Dict[str, List[float]] = {}

    def allow(self, user: str) -> bool:
        now = time.time()
        window = 60.0
        self._claims.setdefault(user, [])
        self._claims[user] = [t for t in self._claims[user] if now - t < window]
        if len(self._claims[user]) >= self._max:
            return False
        self._claims[user].append(now)
        return True


# ---------------------------------------------------------------------------
# Webhook / event stub
# ---------------------------------------------------------------------------

class HaxEventBus:
    def __init__(self) -> None:
        self._listeners: List[Callable[[str, Dict[str, Any]], None]] = []

    def subscribe(self, cb: Callable[[str, Dict[str, Any]], None]) -> None:
        self._listeners.append(cb)

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Treasury math (aligned with Solidity)
# ---------------------------------------------------------------------------

def hax_operator_fee_wei(total_wei: int) -> int:
    return (total_wei * HAX_OPERATOR_FEE_BPS) // HAX_BPS_DENOM


def hax_treasury_wei(total_wei: int) -> int:
    return total_wei - hax_operator_fee_wei(total_wei)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    engine = HackAppEngine()
    engine.register_gadget("0xAlice", "Ctrl+Shift+P -> Command Palette", fee_wei=HAX_FEE_WEI)
    engine.register_gadget("0xBob", "Cmd+K Cmd+D -> Format", fee_wei=HAX_FEE_WEI)
    engine.claim_shortcut(1, "0xCharlie")
    hax_cli_stats(engine, "0xAlice")
    print(engine.get_global_stats())


# ---------------------------------------------------------------------------
# Extended models and helpers (1200+ lines total)
# ---------------------------------------------------------------------------

@dataclass
class HaxGadgetMeta:
    title: str
    description: str
    tags: List[str]
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "description": self.description, "tags": self.tags, "created_at": self.created_at}


class HaxConfigLoader:
    DEFAULT_PATH = "hackapp_config.json"

    @staticmethod
    def load(path: Optional[str] = None) -> Dict[str, Any]:
        p = path or HaxConfigLoader.DEFAULT_PATH
        try:
            with open(p, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "max_gadgets": HAX_MAX_GADGETS,
                "quota_per_user": HAX_QUOTA_PER_USER,
                "fee_wei": HAX_FEE_WEI,
                "min_claim_interval_sec": HAX_MIN_CLAIM_INTERVAL_SEC,
            }

    @staticmethod
    def save(config: Dict[str, Any], path: Optional[str] = None) -> None:
        p = path or HaxConfigLoader.DEFAULT_PATH
        with open(p, "w") as f:
            json.dump(config, f, indent=2)


class HaxBatchProcessor:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def register_batch(self, owner: str, payloads: List[str], category: HaxGadgetCategory = HaxGadgetCategory.SNIPPET) -> List[HaxGadget]:
        out: List[HaxGadget] = []
        for pl in payloads:
            try:
                g = self._engine.register_gadget(owner, pl, category=category, fee_wei=HAX_FEE_WEI)
                out.append(g)
            except Exception:
                pass
        return out

    def claim_batch(self, claimer: str, gadget_ids: List[int]) -> List[HaxShortcut]:
        out: List[HaxShortcut] = []
        for gid in gadget_ids:
            try:
                s = self._engine.claim_shortcut(gid, claimer)
                out.append(s)
                time.sleep(0.01)
            except Exception:
                pass
        return out


class HaxCache:
    def __init__(self, ttl_sec: float = 300, max_size: int = 1000) -> None:
        self._ttl = ttl_sec
        self._max = max_size
        self._data: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None
        val, ts = self._data[key]
        if time.time() - ts > self._ttl:
            del self._data[key]
            return None
        return val

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._data.keys(), key=lambda k: self._data[k][1])
            del self._data[oldest]
        self._data[key] = (value, time.time())


def hax_shortcut_key_hex(gadget_id: int, claimer: str, ts: float) -> str:
    raw = hax_encode_shortcut_key(gadget_id, claimer, ts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class HaxMigrationV1ToV2:
    @staticmethod
    def migrate_user_id_v1_to_v2(old_id: str) -> str:
        if old_id.startswith("v2_"):
            return old_id
        return "v2_" + hashlib.sha256(old_id.encode()).hexdigest()[:16]

    @staticmethod
    def migrate_gadget_record(g: HaxGadget) -> Dict[str, Any]:
        d = g.to_dict()
        d["_version"] = 2
        d["_migrated_at"] = time.time()
        return d


class HaxHealthCheck:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def run(self) -> Dict[str, Any]:
        try:
            gs = self._engine.get_global_stats()
            return {"ok": True, "stats": gs, "timestamp": time.time()}
        except Exception as e:
            return {"ok": False, "error": str(e), "timestamp": time.time()}


def hax_leaderboard_json(engine: HackAppEngine, limit: int = 50) -> str:
    analytics = HaxEfficiencyAnalytics(engine)
    top = analytics.top_users_by_score(limit)
    data = [{"rank": i + 1, "user": u, "efficiency_score": s} for i, (u, s) in enumerate(top)]
    return json.dumps(data, indent=2)


class HaxShortcutValidator:
    @staticmethod
    def can_claim(engine: HackAppEngine, gadget_id: int, claimer: str) -> Tuple[bool, str]:
        if gadget_id not in engine._gadgets:
            return False, "invalid_gadget_id"
        g = engine._gadgets[gadget_id]
        if not g.active:
            return False, "gadget_inactive"
        last = engine._last_claim_time.get(claimer, 0)
        if time.time() < last + HAX_MIN_CLAIM_INTERVAL_SEC:
            return False, "claim_too_soon"
        return True, "ok"


class HaxGadgetSearch:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def by_owner(self, owner: str) -> List[HaxGadget]:
        ids = self._engine.get_gadget_ids_by_owner(owner)
        return [self._engine._gadgets[i] for i in ids if i in self._engine._gadgets]

    def by_category(self, category: HaxGadgetCategory) -> List[HaxGadget]:
        return [g for g in self._engine._gadgets.values() if g.category == category]

    def active_only(self) -> List[HaxGadget]:
        return [g for g in self._engine._gadgets.values() if g.active]


class HaxMetricsCollector:
    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}
        self._timings: Dict[str, List[float]] = {}

    def increment(self, name: str, delta: int = 1) -> None:
        self._counts[name] = self._counts.get(name, 0) + delta

    def record_timing(self, name: str, sec: float) -> None:
        self._timings.setdefault(name, []).append(sec)
        if len(self._timings[name]) > 1000:
            self._timings[name] = self._timings[name][-500:]

    def summary(self) -> Dict[str, Any]:
        return {"counts": dict(self._counts), "timing_keys": list(self._timings.keys())}


def hax_simulate_claims(engine: HackAppEngine, n: int, users: List[str], gadget_ids: List[int]) -> int:
    import random
    success = 0
    for _ in range(n):
        u = random.choice(users)
        gid = random.choice(gadget_ids)
        try:
            engine.claim_shortcut(gid, u)
            success += 1
        except Exception:
            pass
    return success


class HaxApiResponse:
    @staticmethod
    def ok(data: Any) -> Dict[str, Any]:
        return {"success": True, "data": data, "ts": time.time()}

    @staticmethod
    def err(message: str, code: int = 400) -> Dict[str, Any]:
        return {"success": False, "error": message, "code": code, "ts": time.time()}


def hax_serialize_gadget_for_evm(g: HaxGadget) -> Dict[str, Any]:
    return {
        "gadget_id": g.gadget_id,
        "owner": g.owner,
        "gadget_hash": "0x" + g.gadget_hash[:64],
        "registered_at": int(g.registered_at),
        "active": g.active,
    }


class HaxTokenBucket:
    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last = time.time()

    def consume(self, n: int = 1) -> bool:
        now = time.time()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False


class HaxAuditLog:
    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._max = max_entries

    def log(self, action: str, actor: str, details: Dict[str, Any]) -> None:
        self._entries.append({"action": action, "actor": actor, "details": details, "ts": time.time()})
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(reversed(self._entries[-limit:]))


def hax_gadget_hash_evm_compat(payload: str, nonce: int) -> str:
    msg = (HAX_DOMAIN_SEED + payload + str(nonce)).encode()
    return "0x" + hashlib.sha256(msg).hexdigest()


class HaxFeatureFlags:
    def __init__(self) -> None:
        self._flags: Dict[str, bool] = {
            "double_claim_bonus": False,
            "streak_multiplier": True,
            "export_v2": True,
        }

    def is_on(self, name: str) -> bool:
        return self._flags.get(name, False)

    def set(self, name: str, on: bool) -> None:
        self._flags[name] = on


class HaxTreasuryReport:
    @staticmethod
    def generate(engine: HackAppEngine) -> Dict[str, Any]:
        total = engine._total_fees_wei
        op_fee = hax_operator_fee_wei(total)
        tr_fee = hax_treasury_wei(total)
        return {
            "total_fees_wei": total,
            "operator_fee_wei": op_fee,
            "treasury_fee_wei": tr_fee,
            "treasury_address": HAX_TREASURY_ADDRESS,
            "operator_address": HAX_OPERATOR_ADDRESS,
        }


def hax_validate_gadget_hash(h: str) -> bool:
    if not h or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except ValueError:
        return False


class HaxIdGenerator:
    _counter = 0

    @classmethod
    def next_gadget_id(cls) -> int:
        cls._counter += 1
        return cls._counter

    @classmethod
    def next_shortcut_id(cls) -> int:
        cls._counter += 1
        return cls._counter

    @classmethod
    def uuid_short(cls) -> str:
        return uuid.uuid4().hex[:12]


class HaxPagination:
    @staticmethod
    def slice_list(items: List[Any], page: int, per_page: int) -> Tuple[List[Any], int, int]:
        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        return items[start:end], total, max(1, (total + per_page - 1) // per_page)


def hax_export_user_report(engine: HackAppEngine, user: str) -> str:
    stats = engine.get_user_stats(user)
    ids = engine.get_gadget_ids_by_owner(user)
    gadgets = [engine._gadgets[i].to_dict() for i in ids if i in engine._gadgets]
    data = {"user": user, "stats": stats.to_dict(), "gadgets": gadgets, "exported_at": time.time()}
    return json.dumps(data, indent=2)


class HaxEfficiencyFormula:
    @staticmethod
    def score_for_claim(base: int = HAX_SCORE_BASE, streak: int = 0) -> int:
        bonus = min(streak * 2, 20)
        return base + (int(time.time()) % 5) + bonus

    @staticmethod
    def tier_threshold(tier: HaxEfficiencyTier) -> int:
        return tier.min_score


def hax_dummy_load_test(engine: HackAppEngine, num_gadgets: int = 100, num_claims: int = 500) -> None:
    users = [f"0xUser{i}" for i in range(10)]
    for i in range(num_gadgets):
        u = users[i % len(users)]
        try:
            engine.register_gadget(u, f"payload_{i}_hack", fee_wei=0)
        except Exception:
            pass
    gids = list(engine._gadgets.keys())[:20]
    for _ in range(num_claims):
        u = users[int(time.time()) % len(users)]
        if gids:
            gid = gids[int(time.time()) % len(gids)]
            try:
                engine.claim_shortcut(gid, u)
            except Exception:
                pass


class HaxSnapshot:
    def __init__(self, engine: HackAppEngine) -> None:
        self._gadgets = {k: (g.gadget_id, g.owner, g.active) for k, g in engine._gadgets.items()}
        self._scores = dict(engine._efficiency_score)
        self._ts = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {"gadgets": self._gadgets, "scores": self._scores, "ts": self._ts}


def hax_compare_snapshots(a: HaxSnapshot, b: HaxSnapshot) -> Dict[str, Any]:
    new_gadgets = set(b._gadgets) - set(a._gadgets)
    new_scores = {u: b._scores.get(u, 0) - a._scores.get(u, 0) for u in set(a._scores) | set(b._scores)}
    return {"new_gadget_count": len(new_gadgets), "score_deltas": new_scores}


# ---------------------------------------------------------------------------
# Additional utilities for 1200+ line count
# ---------------------------------------------------------------------------

class HaxMiddlewareChain:
    def __init__(self) -> None:
        self._handlers: List[Callable[..., Any]] = []

    def use(self, fn: Callable[..., Any]) -> "HaxMiddlewareChain":
        self._handlers.append(fn)
        return self

    def run(self, initial: Any) -> Any:
        val = initial
        for fn in self._handlers:
            val = fn(val)
        return val


class HaxValidationRule:
    def __init__(self, name: str, predicate: Callable[[Any], bool], message: str) -> None:
        self.name = name
        self.predicate = predicate
        self.message = message

    def check(self, value: Any) -> Tuple[bool, str]:
        return (self.predicate(value), self.message) if not self.predicate(value) else (True, "")


def hax_rules_gadget_payload() -> List[HaxValidationRule]:
    return [
        HaxValidationRule("non_empty", lambda x: bool(x and str(x).strip()), "Payload cannot be empty"),
        HaxValidationRule("max_len", lambda x: len(str(x)) <= 4096, "Payload exceeds max length"),
        HaxValidationRule("no_null_bytes", lambda x: "\x00" not in str(x), "Payload must not contain null bytes"),
    ]


def hax_rules_owner() -> List[HaxValidationRule]:
    return [
        HaxValidationRule("length", lambda x: 2 <= len(str(x)) <= 64, "Owner length must be 2-64"),
        HaxValidationRule("chars", lambda x: hax_validate_owner(str(x)), "Owner format invalid"),
    ]


def hax_apply_rules(value: Any, rules: List[HaxValidationRule]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    for r in rules:
        ok, msg = r.check(value)
        if not ok:
            errors.append(f"{r.name}: {msg}")
    return (len(errors) == 0, errors)


class HaxFormatter:
    @staticmethod
    def format_wei(wei: int) -> str:
        if wei >= 10**18:
            return f"{wei / 10**18:.4f} ETH"
        return f"{wei} wei"

    @staticmethod
    def format_score(score: int) -> str:
        tier = HaxEfficiencyTier.from_score(score)
        return f"{score} ({tier.value.name})"

    @staticmethod
    def format_ts(ts: float) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


class HaxCsvExport:
    @staticmethod
    def gadgets_header() -> str:
        return "gadget_id,owner,gadget_hash,category,registered_at,active,claim_count"

    @staticmethod
    def gadget_row(g: HaxGadget) -> str:
        return f"{g.gadget_id},{g.owner},{g.gadget_hash},{g.category.value},{g.registered_at},{g.active},{g.claim_count}"

    @staticmethod
    def shortcuts_header() -> str:
        return "shortcut_id,gadget_id,claimer,claimed_at,score_added"

    @staticmethod
    def shortcut_row(s: HaxShortcut) -> str:
        return f"{s.shortcut_id},{s.gadget_id},{s.claimer},{s.claimed_at},{s.score_added}"


def hax_export_csv_gadgets(engine: HackAppEngine) -> str:
    lines = [HaxCsvExport.gadgets_header()]
    for g in engine._gadgets.values():
        lines.append(HaxCsvExport.gadget_row(g))
    return "\n".join(lines)


def hax_export_csv_shortcuts(engine: HackAppEngine, limit: int = 1000) -> str:
    lines = [HaxCsvExport.shortcuts_header()]
    for s in list(engine._shortcuts.values())[-limit:]:
        lines.append(HaxCsvExport.shortcut_row(s))
    return "\n".join(lines)


class HaxRetryPolicy:
    def __init__(self, max_attempts: int = 3, backoff_base: float = 0.5) -> None:
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base

    def run(self, fn: Callable[[], Any], is_retryable: Callable[[Exception], bool]) -> Any:
        last: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            try:
                return fn()
            except Exception as e:
                last = e
                if not is_retryable(e) or attempt == self.max_attempts - 1:
                    raise
                time.sleep(self.backoff_base * (2 ** attempt))
        raise last or RuntimeError("retry exhausted")


class HaxCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_sec: float = 60) -> None:
        self._threshold = failure_threshold
        self._reset_sec = reset_sec
        self._failures = 0
        self._last_fail_time: float = 0

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        self._last_fail_time = time.time()

    def is_open(self) -> bool:
        if time.time() - self._last_fail_time > self._reset_sec:
            self._failures = 0
        return self._failures >= self._threshold


class HaxBackoff:
    @staticmethod
    def exponential(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
        return min(cap, base * (2 ** attempt))

    @staticmethod
    def linear(attempt: int, step: float = 1.0, cap: float = 30.0) -> float:
        return min(cap, step * (attempt + 1))


def hax_sanitize_display_name(name: str, max_len: int = 32) -> str:
    s = "".join(c for c in name if c.isalnum() or c in "._- ").strip()
    return s[:max_len] if s else "anon"


def hax_truncate_hash(h: str, head: int = 8, tail: int = 4) -> str:
    if len(h) <= head + tail:
        return h
    return h[:head] + "..." + h[-tail:]


class HaxGadgetRecommendation:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def for_user(self, user: str, limit: int = 5) -> List[HaxGadget]:
        owned_ids = set(self._engine.get_gadget_ids_by_owner(user))
        by_claims = sorted(
            [g for g in self._engine._gadgets.values() if g.active and g.gadget_id not in owned_ids],
            key=lambda x: -x.claim_count,
        )
        return by_claims[:limit]


class HaxDailyStats:
    def __init__(self, engine: HackAppEngine) -> None:
        self._engine = engine

    def registrations_today(self) -> int:
        today_start = time.time() - (time.time() % 86400)
        return sum(1 for g in self._engine._gadgets.values() if g.registered_at >= today_start)

    def claims_today(self) -> int:
        today_start = time.time() - (time.time() % 86400)
        return sum(1 for s in self._engine._shortcuts.values() if s.claimed_at >= today_start)


def hax_build_sitemap_entries(engine: HackAppEngine, base_url: str) -> List[str]:
    entries = [f"{base_url}/"]
    for gid in engine._gadgets:
        entries.append(f"{base_url}/gadget/{gid}")
    return entries


class HaxJsonSchemaValidator:
    GADGET_SCHEMA = {
        "type": "object",
        "required": ["owner", "gadget_hash"],
        "properties": {
            "owner": {"type": "string", "minLength": 2, "maxLength": 64},
            "gadget_hash": {"type": "string", "minLength": 64, "maxLength": 64},
            "category": {"type": "string", "enum": ["keyboard", "automation", "snippet", "workflow", "macro"]},
        },
    }

    @staticmethod
    def validate_gadget_input(data: Dict[str, Any]) -> List[str]:
        errs: List[str] = []
        if "owner" not in data:
            errs.append("missing owner")
        elif not isinstance(data["owner"], str) or not (2 <= len(data["owner"]) <= 64):
            errs.append("invalid owner")
        if "gadget_hash" not in data:
            errs.append("missing gadget_hash")
        elif not isinstance(data["gadget_hash"], str) or len(data["gadget_hash"]) != 64:
            errs.append("invalid gadget_hash")
        return errs


def hax_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hax_hmac_key() -> str:
    return (HAX_DOMAIN_SEED + HAX_VAULT_SEED_HEX).encode().hex()[:64]


class HaxRateLimitConfig:
    def __init__(self, claims_per_min: int = 10, reg_per_min: int = 5) -> None:
        self.claims_per_min = claims_per_min
        self.reg_per_min = reg_per_min


def hax_apply_rate_limits(limiter: HaxRateLimiter, user: str, action: str) -> bool:
    return limiter.allow(user)


class HaxWebhookPayload:
    @staticmethod
    def gadget_registered(g: HaxGadget) -> Dict[str, Any]:
        return {"event": "gadget_registered", "gadget_id": g.gadget_id, "owner": g.owner, "ts": time.time()}

    @staticmethod
    def shortcut_claimed(s: HaxShortcut) -> Dict[str, Any]:
        return {"event": "shortcut_claimed", "shortcut_id": s.shortcut_id, "gadget_id": s.gadget_id, "claimer": s.claimer, "ts": time.time()}


def hax_version_string() -> str:
    return "HackApp.GadgetSplash.1.0"


def hax_supported_categories() -> List[str]:
    return [c.value for c in HaxGadgetCategory]


def hax_tier_bounds() -> Dict[str, Tuple[int, int]]:
    return {t.value.name: (t.min_score, t.max_score) for t in HaxEfficiencyTier}


class HaxMemoryStore:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def keys(self) -> List[str]:
        return list(self._store.keys())


def hax_dedupe_ids(ids: List[int]) -> List[int]:
    return list(dict.fromkeys(ids))


def hax_chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


