"""Versioned boundary configuration. Configuration cannot grant runtime evidence."""

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openbot.contracts import strict_json


class CapabilityUnavailable(ValueError):
    pass


class ProfileConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["1.1"]
    profile_id: str = Field(pattern=r"^pro_[A-Za-z0-9_-]{4,96}$")
    workspace: str
    mode: Literal["CONNECTED", "LOCAL_MODEL", "OFFLINE"] = "OFFLINE"
    max_active_tasks: Literal[1] = 1
    model_endpoint: str | None = Field(default=None, repr=False)
    model_secret_ref: str | None = Field(default=None, min_length=1, repr=False)
    feishu_enabled: bool = False
    cloud_fallback: Literal[False] = False
    sdk_max_retries: Literal[0] = 0
    host_execution: Literal[False] = False
    runtime_downloads: Literal[False] = False
    external_exporter: Literal[False] = False

    @model_validator(mode="after")
    def check_policy(self) -> "ProfileConfig":
        directory = Path(self.workspace)
        if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
            raise ValueError("Workspace must be an existing absolute directory")
        if os.name == "posix" and directory.stat().st_mode & 0o022:
            raise ValueError("Workspace must not be writable by other users")
        if self.mode == "OFFLINE" and self.feishu_enabled:
            raise ValueError("OFFLINE disables Feishu")
        if self.model_endpoint:
            endpoint = urlsplit(self.model_endpoint)
            if (
                endpoint.scheme not in {"http", "https"}
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
            ):
                raise ValueError("Invalid model endpoint")
            if self.mode != "CONNECTED" and endpoint.hostname not in {"127.0.0.1", "::1"}:
                raise ValueError(
                    "Local model requires a loopback endpoint and separate qualification"
                )
            if self.mode == "CONNECTED" and endpoint.scheme != "https":
                raise ValueError("Cloud endpoint requires TLS")
        return self


def load_config(raw: str | bytes) -> ProfileConfig:
    return ProfileConfig.model_validate(strict_json(raw))


def authorize_connection(config: ProfileConfig, kind: str) -> str:
    if kind == "cloud_model" and config.mode == "CONNECTED":
        if config.model_endpoint and config.model_secret_ref:
            return config.model_endpoint
    # Actual local-runner/egress proof belongs to OB-026; a config bool cannot provide it.
    raise CapabilityUnavailable("CAPABILITY_UNAVAILABLE: connection is not qualified")
