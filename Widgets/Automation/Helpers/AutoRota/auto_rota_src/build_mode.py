"""Build mode for Auto Rota: run one controlled pass of a matching Mesmer BuildMgr build.

Runtime-only (touches Py4GWCoreLib). The resolved build instance is private to Auto Rota and has
its fallback disabled, so a pass never runs HeroAI's generic HandleCombat (auto-attack, target
calls, shared combat_handler mutations). A pass is driven one next() per frame by the widget and
is closed after _PASS_TIMEOUT_S.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from typing import Optional

from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import Agent
from Py4GWCoreLib import Player
from Py4GWCoreLib import Profession
from Py4GWCoreLib.BuildMgr import BuildMgr
from Py4GWCoreLib.BuildMgr import BuildRegistry
from Py4GWCoreLib.HeroAI.combat import MAX_SKILLS

from .decide import is_eligible_build
from .model import BuildCandidate

_PASS_TIMEOUT_S = 0.5

BarSignature = tuple[int, int, tuple[int, ...]]


@dataclass(frozen=True)
class BuildPassOutcome:
    cast: Optional[tuple[int, int]]  # (skill_id, target_agent_id) queued by the build, if any
    error: Optional[str] = None


def _bar_signature() -> BarSignature:
    primary, secondary = Agent.GetProfessions(Player.GetAgentID())
    skills = tuple(int(GLOBAL_CACHE.SkillBar.GetSkillIDBySlot(slot) or 0) for slot in range(1, MAX_SKILLS + 1))
    return (int(primary), int(secondary), skills)


def _candidate_for(build: BuildMgr) -> BuildCandidate:
    return BuildCandidate(
        primary_is_mesmer=build.required_primary == Profession.Mesmer,
        is_fallback_candidate=bool(build.is_fallback_candidate),
        overrides_skill_casting=type(build).ProcessSkillCasting is not BuildMgr.ProcessSkillCasting,
    )


class BuildMode:
    def __init__(self) -> None:
        self._registry: Optional[BuildRegistry] = None
        self._signature: Optional[BarSignature] = None
        self._build: Optional[BuildMgr] = None
        self._pass: Optional[Generator[Any, Any, Any]] = None
        self._pass_started_s: float = 0.0
        self._pending: bool = False
        self._pending_since_s: float = 0.0

    @property
    def build_name(self) -> Optional[str]:
        return self._build.build_name if self._build is not None else None

    @property
    def busy(self) -> bool:
        pending = self._pending and time.monotonic() - self._pending_since_s <= _PASS_TIMEOUT_S
        return pending or self._pass is not None

    def blocked_skill_ids(self) -> list[int]:
        """Skills owned by the active build; the rotation after a pass must not cast them."""
        return list(self._build.GetBlockedSkills()) if self._build is not None else []

    def refresh(self) -> None:
        """Re-resolve the build when the bar signature changes. Never swaps builds mid-pass."""
        if self.busy:
            return
        signature = _bar_signature()
        if signature == self._signature:
            return
        self._signature = signature
        self._build = None  # stays None if resolution raises; the widget logs the error
        self._build = self._resolve(signature)

    def _resolve(self, signature: BarSignature) -> Optional[BuildMgr]:
        primary, secondary, skills = signature
        if self._registry is None:
            self._registry = BuildRegistry()
        build = self._registry.GetBestBuild(
            current_primary=Profession(primary),
            current_secondary=Profession(secondary),
            current_skills=list(skills),
        )
        if build is None or not is_eligible_build(_candidate_for(build)):
            return None
        build.SetFallback(None, None)
        return build

    def request_pass(self) -> None:
        self._pending = True
        self._pending_since_s = time.monotonic()

    def cancel(self) -> None:
        """Drop any pending request and close a running pass without reporting an outcome."""
        self._pending = False
        if self._pass is not None:
            try:
                self._pass.close()
            except Exception:
                pass  # the pass is being abandoned; nothing to report
            finally:
                self._pass = None

    def advance(self) -> Optional[BuildPassOutcome]:
        """Call once per frame. Returns an outcome when a pass finishes, else None."""
        if self._pass is not None:
            if time.monotonic() - self._pass_started_s > _PASS_TIMEOUT_S:
                return self._finish(None)  # stale pass (widget was not ticking); do not step it again
        else:
            if not self._pending:
                return None
            self._pending = False
            if time.monotonic() - self._pending_since_s > _PASS_TIMEOUT_S:
                return None  # stale request (widget was not ticking); drop it silently
            if self._build is None:
                return BuildPassOutcome(cast=None)
            self._build.last_cast = None
            self._pass = self._build.ProcessSkillCasting()
            self._pass_started_s = time.monotonic()
        try:
            next(self._pass)
        except StopIteration:
            return self._finish(None)
        except Exception as exc:
            return self._finish(str(exc))
        if time.monotonic() - self._pass_started_s > _PASS_TIMEOUT_S:
            return self._finish(None)
        return None

    def _finish(self, error: Optional[str]) -> BuildPassOutcome:
        if self._pass is not None:
            try:
                self._pass.close()
            except Exception as exc:
                error = error or f"close: {exc}"
            finally:
                self._pass = None
        cast = self._build.last_cast if self._build is not None else None
        return BuildPassOutcome(cast=cast, error=error)
