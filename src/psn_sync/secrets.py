"""Fetch the NPSSO token: from $PSN_NPSSO (local/dry-run testing) or, in CI,
from GCP Secret Manager.
"""

from __future__ import annotations

from .config import Config


def fetch_npsso(config: Config) -> str:
    if config.npsso_override:
        return config.npsso_override

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = (
        f"projects/{config.gcp_project}/secrets/"
        f"{config.npsso_secret_name}/versions/latest"
    )
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("utf-8").strip()
