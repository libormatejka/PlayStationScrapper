"""Environment-driven configuration for the sync job."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    gcp_project: str
    bq_dataset: str
    bq_location: str
    npsso_secret_name: str
    npsso_override: str | None  # set via $PSN_NPSSO for local/dry-run testing

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            gcp_project=_require("GCP_PROJECT"),
            bq_dataset=os.environ.get("BQ_DATASET", "psn"),
            bq_location=os.environ.get("BQ_LOCATION", "EU"),
            npsso_secret_name=os.environ.get("NPSSO_SECRET_NAME", "psn-npsso"),
            npsso_override=os.environ.get("PSN_NPSSO"),
        )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value
