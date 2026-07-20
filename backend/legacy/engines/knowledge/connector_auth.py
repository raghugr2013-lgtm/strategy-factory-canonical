"""Phase 2 Stage 4 — Connector authentication models (P4A.0).

Every connector declares its auth mode at registration. The resolver
reads secrets from environment variables — never from code, never
from `.env.example` defaults. Missing secrets cause the connector's
`health` to report `mode="unconfigured"` rather than crash at boot.

Design invariants:
  * `__str__` / `__repr__` NEVER print secret material — every
    concrete auth object redacts.
  * Auth objects are frozen dataclasses; they cannot be mutated after
    construction.
  * `resolve()` is a pure function of the env at call time; it does
    not cache secrets. This means rotating a secret in a live process
    is a supervisor restart (documented in the connector's health
    endpoint).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol


# ── Secret loading ───────────────────────────────────────────────────

def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v if (v and v.strip()) else None


# ── Auth modes (Protocol pattern) ────────────────────────────────────

class ConnectorAuth(Protocol):
    """Every auth object exposes `mode` and `is_configured()`.

    `mode` is a stable string used by health snapshots.
    `is_configured()` returns True iff every required env secret is
    present. Callers use this to decide whether the connector is
    healthy.
    """
    mode: str

    def is_configured(self) -> bool: ...
    def headers(self) -> Dict[str, str]: ...
    def to_health_dict(self) -> Dict[str, Any]: ...


# ── Concrete implementations ─────────────────────────────────────────

@dataclass(frozen=True)
class NoAuth:
    """No authentication needed. Always configured."""
    mode: str = "none"

    def is_configured(self) -> bool:
        return True

    def headers(self) -> Dict[str, str]:
        return {}

    def to_health_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "configured": True}

    def __repr__(self) -> str:
        return "NoAuth()"


@dataclass(frozen=True)
class ApiKeyAuth:
    """API-key auth via an X-API-Key or query-param header.

    Attributes:
        env_var: Env var name that holds the key.
        header_name: The header to attach when calling.
        required: True → key MUST be set for the connector to be healthy.
                  False → optional (raises rate limits but connector
                  still works when absent).
    """
    env_var:     str
    header_name: str  = "X-API-Key"
    required:    bool = False
    mode:        str  = "api_key"

    def is_configured(self) -> bool:
        return (not self.required) or (_env(self.env_var) is not None)

    def headers(self) -> Dict[str, str]:
        key = _env(self.env_var)
        return {self.header_name: key} if key else {}

    def to_health_dict(self) -> Dict[str, Any]:
        return {
            "mode":       self.mode,
            "env_var":    self.env_var,
            "required":   self.required,
            "configured": self.is_configured(),
            # NEVER return the actual key value
        }

    def __repr__(self) -> str:
        return f"ApiKeyAuth(env_var={self.env_var!r}, required={self.required})"


@dataclass(frozen=True)
class BearerAuth:
    """Bearer-token auth via the Authorization header."""
    env_var:  str
    required: bool = True
    mode:     str  = "bearer"

    def is_configured(self) -> bool:
        return (not self.required) or (_env(self.env_var) is not None)

    def headers(self) -> Dict[str, str]:
        tok = _env(self.env_var)
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def to_health_dict(self) -> Dict[str, Any]:
        return {
            "mode":       self.mode,
            "env_var":    self.env_var,
            "required":   self.required,
            "configured": self.is_configured(),
        }

    def __repr__(self) -> str:
        return f"BearerAuth(env_var={self.env_var!r}, required={self.required})"


@dataclass(frozen=True)
class OAuthClientCredentials:
    """OAuth2 client-credentials flow (client_id + client_secret →
    access_token via a token endpoint).

    Token acquisition is DEFERRED to the connector's HTTP client — this
    object only knows the env-var names and the token endpoint URL.
    Concrete OAuth flows land per-connector in Stage 4 when a real
    prop-firm portal actually requires them.
    """
    client_id_env:     str
    client_secret_env: str
    token_url:         str
    required:          bool = True
    mode:              str  = "oauth_cc"

    def is_configured(self) -> bool:
        if not self.required:
            return True
        return _env(self.client_id_env) is not None and _env(self.client_secret_env) is not None

    def headers(self) -> Dict[str, str]:
        # Actual token fetch is deferred to the connector — this object
        # only signals mode. The connector calls resolve_token()
        # separately when it needs to make a request.
        return {}

    def to_health_dict(self) -> Dict[str, Any]:
        return {
            "mode":                  self.mode,
            "client_id_env":         self.client_id_env,
            "client_secret_env":     self.client_secret_env,
            "token_url":             self.token_url,
            "required":              self.required,
            "configured":            self.is_configured(),
        }

    def __repr__(self) -> str:
        return (
            f"OAuthClientCredentials(client_id_env={self.client_id_env!r}, "
            f"token_url={self.token_url!r}, required={self.required})"
        )
