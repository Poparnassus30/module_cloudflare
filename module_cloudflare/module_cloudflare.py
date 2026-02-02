import json
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests


API_BASE = "https://api.cloudflare.com/client/v4"


@dataclass(frozen=True)
class TunnelRoute:
    hostname: str
    service: str


class CloudflareClient:
    """
    Minimal Cloudflare API client focused on Cloudflare Tunnel remote-managed ingress routes.
    """

    def __init__(self, api_token: str, account_id: str):
        if not api_token:
            raise ValueError("Missing api_token")
        if not account_id:
            raise ValueError("Missing account_id")

        self.api_token = api_token
        self.account_id = account_id

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )

    def _get(self, path: str) -> dict:
        url = f"{API_BASE}{path}"
        r = self.session.get(url, timeout=20)

        try:
            data = r.json()
        except Exception:
            raise RuntimeError(f"Non-JSON response (HTTP {r.status_code}): {r.text[:300]}")

        if not r.ok or not data.get("success", False):
            raise RuntimeError(f"Cloudflare API error (HTTP {r.status_code}): {json.dumps(data, indent=2)[:2000]}")

        return data["result"]

    def get_tunnel_configuration(self, tunnel_id: str) -> dict:
        """
        Returns the tunnel configuration object that includes remote-managed ingress rules.
        Endpoint: GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
        """
        if not tunnel_id:
            raise ValueError("Missing tunnel_id")

        return self._get(f"/accounts/{self.account_id}/cfd_tunnel/{tunnel_id}/configurations")

    def get_tunnel_routes(self, tunnel_id: str) -> Tuple[List[TunnelRoute], Optional[str]]:
        """
        Returns:
          - a list of (hostname -> service) ingress routes
          - the fallback service (often http_status:404) if present
        """
        result = self.get_tunnel_configuration(tunnel_id)

        config = (result.get("config") or {})
        ingress = (config.get("ingress") or [])

        routes: List[TunnelRoute] = []
        fallback: Optional[str] = None

        for rule in ingress:
            hostname = rule.get("hostname")
            service = rule.get("service")
            if hostname and service:
                routes.append(TunnelRoute(hostname=hostname, service=service))

        # Fallback rule: typically the last ingress item with no hostname
        for rule in reversed(ingress):
            if rule.get("service") and not rule.get("hostname"):
                fallback = rule.get("service")
                break

        routes.sort(key=lambda r: r.hostname)
        return routes, fallback


def load_env() -> Tuple[str, str, str]:
    """
    Load required env vars. Keep it simple for now.
    """
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    tunnel_id = os.getenv("CLOUDFLARE_TUNNEL_ID", "")

    missing = [k for k, v in [
        ("CLOUDFLARE_API_TOKEN", token),
        ("CLOUDFLARE_ACCOUNT_ID", account_id),
        ("CLOUDFLARE_TUNNEL_ID", tunnel_id),
    ] if not v]

    if missing:
        raise RuntimeError("Missing env var(s): " + ", ".join(missing))

    return token, account_id, tunnel_id
