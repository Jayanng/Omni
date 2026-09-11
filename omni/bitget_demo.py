"""Private Bitget account access through the official Agent Hub CLI (``bgc``).

All calls are routed to Bitget's Demo (paper) environment with
``--paper-trading``. The CLI adds the ``paptrading`` header for private calls.

No withdrawal, transfer, or account-settings write is exposed here by design:
the agent must be structurally incapable of moving funds out.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

from .config import Config


class DemoCliError(RuntimeError):
    def __init__(self, message: str, payload: dict | None = None):
        super().__init__(message)
        self.payload = payload or {}


@dataclass
class CliResult:
    argv: list
    stdout: str
    stderr: str
    exit_code: int
    data: dict | None
    raw_envelope: dict | None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.data is not None


class DemoClient:
    """Thin, auditable wrapper around the official Bitget Agent Hub CLI."""

    def __init__(self, config: Config):
        self.config = config
        self.calls: list[dict] = []

    # -- core ---------------------------------------------------------------

    def _subprocess_env(self) -> dict:
        """Environment for the CLI child process.

        Credentials are injected here from the loaded config, so a populated
        ``.env`` is sufficient and Omni does not depend on the caller's shell
        having exported anything.
        """
        env = dict(os.environ)
        if self.config.api_key:
            env["BITGET_API_KEY"] = self.config.api_key
        if self.config.secret_key:
            env["BITGET_SECRET_KEY"] = self.config.secret_key
        if self.config.passphrase:
            env["BITGET_PASSPHRASE"] = self.config.passphrase
        return env

    def call(self, args: list, timeout: int = 60, allow_failure: bool = False) -> CliResult:
        argv = self.config.bgc_argv(args + ["--paper-trading", "--pretty"])
        proc = subprocess.run(  # noqa: S603 - argv is constructed locally
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self._subprocess_env(),
        )
        stdout, stderr, code = proc.stdout.strip(), proc.stderr.strip(), proc.returncode

        envelope, data = None, None
        for candidate in (stdout, stderr):
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                envelope = parsed
                data = parsed.get("data")
                break

        result = CliResult(argv, stdout, stderr, code, data, envelope)
        self.calls.append(
            {
                "argv": " ".join(args),
                "exit_code": code,
                "ok": bool(result.ok),
                "endpoint": (envelope or {}).get("endpoint"),
                "request_time": (envelope or {}).get("requestTime"),
            }
        )

        if not result.ok and not allow_failure:
            detail = ""
            if isinstance(envelope, dict) and isinstance(envelope.get("error"), dict):
                detail = envelope["error"].get("message", "")
            raise DemoCliError(detail or stderr or stdout or "cli call failed", envelope)
        return result

    # -- reads --------------------------------------------------------------

    def account_overview(self, attempts: int = 3) -> dict:
        """Return a normalised snapshot.

        The composite CLI verb nests every section as ``{ok, data}``. Flattening
        it here keeps the rest of the code honest: a failed section is surfaced
        instead of silently reading as zero. The read is retried because the
        composite call can occasionally return an envelope without the assets
        payload, and a silent empty result would corrupt the risk model.
        """
        last_raw: dict = {}
        for attempt in range(attempts):
            raw = self.call(["account_overview"]).data or {}
            last_raw = raw
            normalised = self._normalise_overview(raw)
            if normalised["assets"]:
                return normalised
            if attempt < attempts - 1:
                time.sleep(1.0)
        normalised = self._normalise_overview(last_raw)
        normalised["raw_section_keys"] = sorted(last_raw.keys()) if isinstance(last_raw, dict) else []
        return normalised

    @staticmethod
    def _normalise_overview(raw: dict) -> dict:
        assets: dict = {}
        settings: dict = {}
        funding: list = []
        sections: dict = {}
        if not isinstance(raw, dict):
            return {
                "assets": assets, "settings": settings,
                "funding_assets": funding, "sections": sections,
            }
        for key, value in raw.items():
            if isinstance(value, dict) and "ok" in value:
                sections[key] = {"ok": bool(value.get("ok")), "error": value.get("error")}
                payload = value.get("data")
            else:
                payload = value
            if key == "assets" and isinstance(payload, dict):
                assets = payload
            elif key == "settings" and isinstance(payload, dict):
                settings = payload
            elif key == "fundingAssets" and isinstance(payload, list):
                funding = payload
        return {
            "assets": assets,
            "settings": settings,
            "funding_assets": funding,
            "sections": sections,
        }

    def positions(self, category: str = "USDT-FUTURES") -> list:
        result = self.call(["position", "--action", "info", "--category", category])
        data = result.data or {}
        if isinstance(data, dict):
            return data.get("list") or []
        return data if isinstance(data, list) else []

    def open_orders(self, category: str = "USDT-FUTURES") -> list:
        result = self.call(["order", "--action", "open", "--category", category])
        data = result.data or {}
        if isinstance(data, dict):
            return data.get("list") or []
        return data if isinstance(data, list) else []

    # -- writes -------------------------------------------------------------

    def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        pos_side: str | None = None,
        reduce_only: str | None = None,
        price: str | None = None,
        time_in_force: str | None = None,
        dry_run: bool = False,
    ) -> CliResult:
        args = [
            "order", "--action", "place",
            "--category", category,
            "--symbol", symbol,
            "--side", side,
            "--orderType", order_type,
            "--qty", str(qty),
        ]
        if pos_side:
            args += ["--posSide", pos_side]
        if reduce_only:
            args += ["--reduceOnly", reduce_only]
        if price is not None:
            args += ["--price", str(price)]
        if time_in_force:
            args += ["--timeInForce", time_in_force]
        if dry_run:
            args += ["--dry-run"]
        return self.call(args, allow_failure=True)

    def close_position(
        self,
        category: str,
        symbol: str,
        pos_side: str | None = None,
        dry_run: bool = False,
        confirm: bool = False,
    ) -> CliResult:
        args = ["position", "--action", "close", "--category", category, "--symbol", symbol]
        if pos_side:
            args += ["--posSide", pos_side]
        if dry_run:
            args += ["--dry-run"]
        if confirm:
            args += ["--confirm"]
        return self.call(args, allow_failure=True)
