"""Omni configuration.

Omni reads credentials from the environment first, then from a local ``.env``
file. Secrets are never written to the ledger, to logs, or to stdout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BITGET_REST = "https://api.bitget.com"
DEFAULT_BGC = "bgc"
DEFAULT_BGC_PINNED = ["npx", "--yes", "@bitget-ai/bitget-agent-cli@3.0.0"]

# Reality (rToken) spot fee reference published by Bitget: 0.05% maker and taker.
RTOKEN_FEE_RATE = 0.0005

# Allowed agent actions. Anything outside this set is rejected by policy.
ALLOWED_ACTIONS = (
    "HOLD",
    "HEDGE_STOCK_PERP",
    "REDUCE_PERP",
    "CLOSE_PERP",
)

# Actions that may never be performed by the agent under any circumstance.
FORBIDDEN_ACTIONS = (
    "WITHDRAW",
    "TRANSFER_OUT",
    "INCREASE_LEVERAGE",
    "ADD_RISK",
    "SET_LEVERAGE",
    "ACCOUNT_MODE_CHANGE",
)

# rToken to tradeable stock perpetual mapping. The rToken itself cannot be
# executed in the demo environment, so the mapped perpetual is the instrument
# used to neutralise rToken collateral gap risk.
RTOKEN_TO_STOCK_PERP = {
    "RNVDAUSDT": "NVDAUSDT",
    "RTSLAUSDT": "TSLAUSDT",
    "RAAPLUSDT": "AAPLUSDT",
    "RGOOGLUSDT": "GOOGLUSDT",
    "RMETAUSDT": "METAUSDT",
    "RAMZNUSDT": "AMZNUSDT",
    "RSPYUSDT": "SP500USDT",
    "RQQQUSDT": "NDX100USDT",
}

# Documented default used only when a caller explicitly asks for one. It is NOT
# substituted silently for an unmapped symbol: hedging the wrong instrument is
# worse than refusing to hedge.
DEFAULT_HEDGE_PERP = "NVDAUSDT"


def stock_perp_for(rtoken_symbol: str) -> str:
    """Map an rToken symbol, or an already-mapped perpetual, to a perpetual symbol.

    Returns an empty string when the symbol is not in the mapping. Callers must
    treat that as "no hedge instrument available" and refuse to act, rather than
    defaulting to some other instrument.
    """
    symbol = (rtoken_symbol or "").strip().upper()
    if symbol in RTOKEN_TO_STOCK_PERP:
        return RTOKEN_TO_STOCK_PERP[symbol]
    if symbol.endswith("USDT") and symbol in set(RTOKEN_TO_STOCK_PERP.values()):
        return symbol
    return ""


def mapped_stock_perps() -> tuple:
    """Every stock perpetual the mapping knows about, derived from the map.

    Callers that need a set of hedge symbols take it from here so the list is
    defined once, in config, instead of being re-typed at each call site.
    """
    return tuple(sorted(set(RTOKEN_TO_STOCK_PERP.values())))


def rtoken_for_stock_perp(stock_perp: str) -> str:
    """Reverse lookup: the rToken symbol whose hedge is ``stock_perp``.

    Returns an empty string when the perpetual is not in the mapping, so the
    caller can decide to skip a symbol-specific read instead of inventing one.
    """
    symbol = (stock_perp or "").strip().upper()
    for rtoken, perp in RTOKEN_TO_STOCK_PERP.items():
        if perp == symbol:
            return rtoken
    return ""


def stock_code_for(rtoken_symbol: str) -> str:
    """The underlying equity code for an rToken symbol (RNVDAUSDT -> NVDA)."""
    symbol = (rtoken_symbol or "").strip().upper()
    if symbol.endswith("USDT"):
        symbol = symbol[: -len("USDT")]
    if symbol.startswith("R"):
        symbol = symbol[1:]
    return symbol

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def load_env_file(path: Path) -> dict:
    """Parse a simple KEY=VALUE file. Missing file yields an empty mapping."""
    out: dict = {}
    if not path.exists():
        return out
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _resolve(name: str, file_env: dict) -> str:
    return os.environ.get(name) or file_env.get(name, "")


def _resolve_float(name: str, file_env: dict, default: float) -> float:
    raw = _resolve(name, file_env)
    if raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    api_key: str
    secret_key: str
    passphrase: str
    bgc: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_fallback_model: str
    log_dir: Path
    timeout: int = 30
    # Declared risk inputs, exposed so they are configuration rather than
    # constants buried in the model. Overridable by env or .env.
    risk_threshold_usdt: float = 250.0
    risk_budget_pct: float = 0.10
    policy_max_hedge_notional_usdt: float = 5_000.0

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.secret_key and self.passphrase)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    def bgc_argv(self, args: list) -> list:
        """Build the Agent Hub CLI command. ``OMNI_BGC`` overrides the binary."""
        override = os.environ.get("OMNI_BGC", "").strip()
        if override:
            return override.split() + args
        if self.bgc:
            return [self.bgc] + args
        return DEFAULT_BGC_PINNED + args


def load_config() -> Config:
    env_file = Path(os.environ.get("OMNI_ENV_FILE", str(ROOT / ".env")))
    file_env = load_env_file(env_file)

    bgc = os.environ.get("OMNI_BGC", "")
    if not bgc:
        from shutil import which

        bgc = DEFAULT_BGC if which(DEFAULT_BGC) else ""

    log_dir = Path(os.environ.get("OMNI_LOG_DIR", str(ROOT / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        api_key=_resolve("BITGET_API_KEY", file_env),
        secret_key=_resolve("BITGET_SECRET_KEY", file_env),
        passphrase=_resolve("BITGET_PASSPHRASE", file_env),
        bgc=bgc,
        llm_base_url=_resolve("OMNI_LLM_BASE_URL", file_env) or "https://api.gmi-serving.com/v1",
        llm_api_key=_resolve("OMNI_LLM_API_KEY", file_env),
        llm_model=_resolve("OMNI_LLM_MODEL", file_env) or "deepseek-ai/DeepSeek-V4.1-Flash",
        llm_fallback_model=_resolve("OMNI_LLM_FALLBACK_MODEL", file_env),
        log_dir=log_dir,
        timeout=int(_resolve("OMNI_TIMEOUT", file_env) or 30),
        risk_threshold_usdt=_resolve_float("OMNI_RISK_THRESHOLD_USDT", file_env, 250.0),
        risk_budget_pct=_resolve_float("OMNI_RISK_BUDGET_PCT", file_env, 0.10),
        policy_max_hedge_notional_usdt=_resolve_float(
            "OMNI_POLICY_MAX_HEDGE_NOTIONAL", file_env, 5_000.0
        ),
    )
