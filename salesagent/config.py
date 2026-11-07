"""Loads config.yaml and environment settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
# On Railway, use the attached volume wherever it is mounted (RAILWAY_VOLUME_MOUNT_PATH), so data survives redeploys.
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.environ.get("SALESAGENT_DATA") or ROOT / "data")


def storage_status() -> dict:
    """Is the data folder on a permanent disk? (On Railway that means an attached volume.)"""
    on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID")
                      or os.environ.get("RAILWAY_SERVICE_ID"))
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    persistent = (not on_railway) or (bool(volume) and str(DATA_DIR).startswith(volume.rstrip("/")))
    return {"data_dir": str(DATA_DIR), "on_railway": on_railway, "volume_mount": volume or None,
            "persistent": persistent}


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@dataclass
class Settings:
    raw: dict

    @property
    def business(self) -> dict:
        return self.raw["business"]

    @property
    def owner(self) -> dict:
        return self.raw["owner"]

    @property
    def sales_team(self) -> list[dict]:
        return self.raw.get("sales_team", [])

    @property
    def booking(self) -> dict:
        return self.raw.get("booking", {})

    @property
    def learning(self) -> dict:
        return self.raw.get("learning", {})

    def rm(self, name: str | None) -> dict | None:
        for r in self.sales_team:
            if r["name"] == name:
                return r
        return self.sales_team[0] if self.sales_team else None

    @property
    def site_persons(self) -> list[dict]:
        return self.raw.get("site_persons", [])

    @property
    def projects(self) -> list[dict]:
        return self.raw.get("projects", [])

    @property
    def agent(self) -> dict:
        return self.raw.get("agent", {})

    @property
    def followups(self) -> dict:
        return self.raw.get("followups", {})

    @property
    def messaging(self) -> dict:
        return self.raw.get("messaging", {})

    @property
    def scoring(self) -> dict:
        return self.raw.get("lead_scoring", {})

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.business.get("timezone", "UTC"))

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def project(self, name: str) -> dict | None:
        for p in self.projects:
            if p["name"].lower() == (name or "").lower():
                return p
        return None

    def unit(self, project: str, unit_type: str) -> dict | None:
        p = self.project(project)
        if not p:
            return None
        for u in p["units"]:
            if u["type"].lower() == (unit_type or "").lower():
                return u
        return None


def writable_config_path() -> Path:
    """Where the dashboard's Settings page saves the config (on the cloud disk when deployed)."""
    custom = os.environ.get("SALESAGENT_CONFIG")
    if custom:
        path = Path(custom)
        # A relative name is kept on the data disk, so it survives redeploys.
        return path if path.is_absolute() else DATA_DIR / path
    return DATA_DIR / "config.yaml"


def config_path() -> Path:
    for path in (writable_config_path(), ROOT / "config.yaml"):
        if path.exists():
            return path
    return ROOT / "config.example.yaml"


def validate_config(raw) -> list[str]:
    errs = []
    if not isinstance(raw, dict):
        return ["The settings must be a YAML mapping (key: value lines)."]
    for key in ("business", "owner"):
        if not raw.get(key):
            errs.append(f"Missing section '{key}'.")
    if raw.get("owner") and not raw["owner"].get("phone"):
        errs.append("owner.phone is required.")
    for p in raw.get("projects") or []:
        if not p.get("name") or not p.get("units"):
            errs.append("Every project needs a name and units.")
            continue
        for u in p["units"]:
            for k in ("type", "list_price", "floor_price"):
                if k not in u:
                    errs.append(f"{p['name']}: a unit is missing '{k}'.")
            lp, fp = u.get("list_price"), u.get("floor_price")
            if not isinstance(lp, (int, float)) or not isinstance(fp, (int, float)):
                errs.append(f"{p['name']} {u.get('type')}: prices must be numbers.")
            elif fp > lp:
                errs.append(f"{p['name']} {u.get('type')}: floor price is above list price.")
    for r in raw.get("sales_team") or []:
        if not r.get("name") or not r.get("phone"):
            errs.append("Every salesperson needs a name and phone.")
    return errs


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    with open(config_path()) as f:
        return Settings(yaml.safe_load(f))


def reload_settings() -> None:
    get_settings.cache_clear()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
