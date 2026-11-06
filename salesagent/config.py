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
DATA_DIR = Path(os.environ.get("SALESAGENT_DATA", ROOT / "data"))


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = Path(os.environ.get("SALESAGENT_CONFIG", ROOT / "config.yaml"))
    if not path.exists():
        path = ROOT / "config.example.yaml"
    with open(path) as f:
        return Settings(yaml.safe_load(f))


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
