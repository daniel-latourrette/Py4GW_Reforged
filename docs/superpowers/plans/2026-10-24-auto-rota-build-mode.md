# Auto Rota — Modo Build: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando a barra corresponde a uma build de Mesmer do repo, cada toque faz primeiro um interrupt importante (ressurreição, cura, elite) pela Auto Rota, senão uma passagem controlada da lógica da build, senão a rotação para as skills fora da build.

**Architecture:** O núcleo puro ganha um limite de nível em `choose_interrupt` e a regra `is_eligible_build`, ambos testados offline. Um módulo novo, `build_mode.py`, deteta a build com o `BuildRegistry`, desliga o fallback e corre a passagem um `next()` por frame com timeout. O `BuildMgr` ganha o campo `last_cast` para se saber o que foi lançado. O widget liga tudo: a tecla trata dos interrupts de imediato e pede a passagem, e o `main()` conduz a passagem.

**Tech Stack:** Python 3.13 32 bits no jogo (testes offline com `python3.12`), Py4GWCoreLib (`BuildMgr`, `BuildRegistry`, HeroAI), PyImGui, `unittest`, Pyright (`npx -y pyright@1.1.390 --pythonversion 3.13`).

**Spec:** `docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md`

**Commits:** autorizados pelo utilizador no branch `feature/auto-rota`, no fim de cada tarefa. Todas as mensagens de commit terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Desvio da spec decidido aqui:** "ocupado durante a passagem" fica no widget (`_build_mode.busy`) e não no `GameAdapter.blocker()`. Assim o adapter não precisa de conhecer o modo build. A spec é atualizada na Task 7.

---

## Estrutura de ficheiros

| Ficheiro | Responsabilidade |
|---|---|
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py` | + `BUILD_MODE_MAX_TIER` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py` | + `BuildCandidate` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py` | + `max_tier` em `choose_interrupt`; + `is_eligible_build` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/build_mode.py` (novo) | Deteção e cache da build, fallback desligado, passagem com timeout, leitura do `last_cast` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py` | + `interrupt_decision`, `rotation_after_build`, `note_external_cast`; máscara de skills no `_sync_combat`; `describe` com texto de "sem alvo" |
| `Widgets/Automation/Helpers/AutoRota/Auto Rota.py` | Integração: tecla, `main()`, janela, tooltip |
| `Py4GWCoreLib/BuildMgr.py` | + campo `last_cast` |
| `Examples and tests/tests/auto_rota/test_auto_rota_decide.py` | + 7 testes |

---

### Task 0: Commit da spec do modo build

- [ ] **Step 1: Commit**

```bash
git add docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md docs/superpowers/plans/2026-10-24-auto-rota-build-mode.md
git commit -m "docs(auto-rota): build mode spec and implementation plan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Limite de nível em `choose_interrupt`

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py`
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py`
- Test: `Examples and tests/tests/auto_rota/test_auto_rota_decide.py`

- [ ] **Step 1: Escrever os testes (falham)**

Acrescentar estes métodos ao fim da classe `ChooseInterruptTests` (antes do `if __name__ == "__main__":`):

```python
    def test_max_tier_skips_casts_below_the_limit(self) -> None:
        casts = [make_cast(agent_id=10, activation_ms=3000), make_cast(agent_id=20)]
        observed = choose_interrupt(casts, [make_slot()], always, max_tier=Tier.ELITE)
        self.assert_choice(observed, None, None, "only long-cast and other casts, limit ELITE")

    def test_max_tier_keeps_casts_within_the_limit(self) -> None:
        casts = [make_cast(agent_id=10, activation_ms=3000), make_cast(agent_id=20, is_healing=True)]
        observed = choose_interrupt(casts, [make_slot()], always, max_tier=Tier.ELITE)
        self.assert_choice(observed, 20, 500, "healing within limit ELITE")

    def test_default_max_tier_allows_every_tier(self) -> None:
        observed = choose_interrupt([make_cast(agent_id=10)], [make_slot()], always)
        self.assert_choice(observed, 10, 500, "OTHER cast with default limit")
```

- [ ] **Step 2: Correr e confirmar que falha**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: 2 erros `TypeError: choose_interrupt() got an unexpected keyword argument 'max_tier'`. O terceiro teste passa já.

- [ ] **Step 3: Acrescentar a constante em `priorities.py`**

Logo a seguir a `LONG_CAST_MS = 2000`:

```python

# In build mode the Auto Rota only interrupts casts up to this tier; lower tiers are left to the
# build's own (damage-optimised) interrupt logic.
BUILD_MODE_MAX_TIER = Tier.ELITE
```

- [ ] **Step 4: Acrescentar `max_tier` a `choose_interrupt` em `decide.py`**

Substituir a função `choose_interrupt` inteira por:

```python
def choose_interrupt(
    casts: Sequence[EnemyCast],
    slots: Sequence[InterruptSlot],
    feasible: FeasibilityCheck,
    max_tier: Tier = Tier.OTHER,
) -> Optional[Decision]:
    """Pick the best (interrupt, cast) pair.

    Casts are tried by lowest tier, then earliest finish (input order breaks exact ties). Casts whose
    tier is above `max_tier` are ignored. For each cast, slots are tried in the given order
    (CombatClass priority order); `feasible` is only called for slots whose reach can hit the cast.
    """
    for cast in sorted(casts, key=_cast_key):
        tier = classify(cast)
        if tier > max_tier:
            break  # casts are sorted by tier, so every remaining cast is above the limit too
        for slot in slots:
            if can_hit(slot.reach, cast.kind) and feasible(slot, cast):
                return Decision(
                    bar_slot=slot.bar_slot,
                    skill_id=slot.skill_id,
                    target_id=cast.agent_id,
                    label=f"Interrupt: {TIER_LABELS[tier]}",
                    enemy_skill_id=cast.skill_id,
                )
    return None
```

- [ ] **Step 5: Correr e confirmar que passa**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 23 tests` … `OK`

- [ ] **Step 6: Commit**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py "Examples and tests/tests/auto_rota/test_auto_rota_decide.py"
git commit -m "feat(auto-rota): tier limit for interrupts in build mode

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Regra de elegibilidade da build

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py`
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py`
- Test: `Examples and tests/tests/auto_rota/test_auto_rota_decide.py`

- [ ] **Step 1: Escrever os testes (falham)**

Imports a juntar no topo do ficheiro de teste (um por linha, por ordem alfabética entre os existentes):

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import is_eligible_build  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import BuildCandidate  # noqa: E402
```

Nova classe antes do `if __name__ == "__main__":`:

```python
class BuildEligibilityTests(unittest.TestCase):
    def assert_eligible(self, candidate: BuildCandidate, expected: bool) -> None:
        observed = is_eligible_build(candidate)
        self.assertEqual(observed, expected, f"is_eligible_build({candidate}) expected={expected} observed={observed}")

    def test_regular_mesmer_build_is_eligible(self) -> None:
        candidate = BuildCandidate(primary_is_mesmer=True, is_fallback_candidate=False, overrides_skill_casting=False)
        self.assert_eligible(candidate, True)

    def test_fallback_candidate_is_rejected(self) -> None:
        candidate = BuildCandidate(primary_is_mesmer=True, is_fallback_candidate=True, overrides_skill_casting=False)
        self.assert_eligible(candidate, False)

    def test_other_profession_is_rejected(self) -> None:
        candidate = BuildCandidate(primary_is_mesmer=False, is_fallback_candidate=False, overrides_skill_casting=False)
        self.assert_eligible(candidate, False)

    def test_build_overriding_skill_casting_is_rejected(self) -> None:
        candidate = BuildCandidate(primary_is_mesmer=True, is_fallback_candidate=False, overrides_skill_casting=True)
        self.assert_eligible(candidate, False)
```

- [ ] **Step 2: Correr e confirmar que falha**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `ImportError: cannot import name 'is_eligible_build'`

- [ ] **Step 3: Acrescentar `BuildCandidate` ao fim de `model.py`**

```python


@dataclass(frozen=True)
class BuildCandidate:
    primary_is_mesmer: bool
    is_fallback_candidate: bool  # e.g. the generic HeroAI build GetBestBuild returns when nothing matches
    overrides_skill_casting: bool  # e.g. farm builds with their own multi-cast ProcessSkillCasting
```

- [ ] **Step 4: Acrescentar `is_eligible_build` a `decide.py`**

Import (junto aos outros de `.model`, por ordem): `from .model import BuildCandidate`

Função no fim do ficheiro:

```python


def is_eligible_build(candidate: BuildCandidate) -> bool:
    """A build can drive one key press only if it is a regular Mesmer combat build."""
    return candidate.primary_is_mesmer and not candidate.is_fallback_candidate and not candidate.overrides_skill_casting
```

- [ ] **Step 5: Correr e confirmar que passa**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 27 tests` … `OK`. Confirmar também que nenhuma linha passa de 120 caracteres: `awk 'length > 120 {print FILENAME": "FNR}' Widgets/Automation/Helpers/AutoRota/auto_rota_src/*.py "Examples and tests/tests/auto_rota/test_auto_rota_decide.py"` não imprime nada. Se a linha do `return` em `is_eligible_build` passar de 120, partir assim:

```python
    return (
        candidate.primary_is_mesmer and not candidate.is_fallback_candidate and not candidate.overrides_skill_casting
    )
```

- [ ] **Step 6: Commit**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py "Examples and tests/tests/auto_rota/test_auto_rota_decide.py"
git commit -m "feat(auto-rota): build eligibility rule

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Campo `last_cast` no `BuildMgr`

**Files:**
- Modify: `Py4GWCoreLib/BuildMgr.py` (perto da linha 67 e da linha 1940)

- [ ] **Step 1: Declarar o campo no `__init__`**

Logo a seguir à linha `self._cached_data: Any = None` (cerca da linha 67):

```python
        # (skill_id, target_agent_id) of the last skill this build queued through CastSkillID.
        self.last_cast: tuple[int, int] | None = None
```

- [ ] **Step 2: Registar em `CastSkillID`**

No método `CastSkillID`, logo a seguir à linha
`GLOBAL_CACHE.SkillBar.UseSkill(slot, target_agent_id=target_agent_id, aftercast_delay=aftercast_delay)`
(cerca da linha 1940; é a primeira das duas ocorrências e fica dentro de `CastSkillID`, não de `CastSkillSlot`):

```python
        self.last_cast = (skill_id, target_agent_id)
```

Confirmar com `grep -n "self.last_cast" Py4GWCoreLib/BuildMgr.py` que aparecem exatamente 2 linhas: a declaração e a atribuição dentro de `CastSkillID`.

- [ ] **Step 3: Pyright**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 Py4GWCoreLib/BuildMgr.py 2>&1 | grep -n "last_cast\|error" | head -40`
Expected: nenhum erro nas linhas acrescentadas (as que têm `last_cast`). Erros que já existiam noutras linhas do `BuildMgr.py` não se corrigem aqui; reportar a contagem total para registo. Não usar `git stash` nem outros comandos que mexam na árvore de trabalho.

- [ ] **Step 4: Commit**

```bash
git add Py4GWCoreLib/BuildMgr.py
git commit -m "feat(buildmgr): record last skill queued by CastSkillID

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Módulo `build_mode.py`

**Files:**
- Create: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/build_mode.py`

Este módulo só corre no jogo. Verifica-se com Pyright aqui e no jogo na Task 8.

APIs usadas (confirmadas): `BuildRegistry()` e `BuildMgr.GetBestBuild(current_primary, current_secondary, current_skills)` (`Py4GWCoreLib/BuildMgr.py:2112, 2274`; o registry tem `GetBestBuild` por herança/composição — **confirmar no Step 1**); `BuildMgr.SetFallback(None, None)` (`BuildMgr.py:161`, faz `ResolveFallback()` devolver `None` em `BuildMgr.py:1571-1575`); `BuildMgr.ProcessSkillCasting()` (`BuildMgr.py:2061`); `BuildMgr.GetBlockedSkills()` (`BuildMgr.py:177`); `BuildMgr.is_fallback_candidate`, `required_primary`, `build_name`; `Agent.GetProfessions(agent_id)`; `GLOBAL_CACHE.SkillBar.GetSkillIDBySlot(slot)` (1-based); `Profession` em `Py4GWCoreLib`.

- [ ] **Step 1: Confirmar onde vive `GetBestBuild`**

Run: `grep -n "class BuildRegistry\|    def GetBestBuild\|    def ResolveBuild" Py4GWCoreLib/BuildMgr.py`
Expected: `GetBestBuild` aparece depois da linha de `class BuildRegistry`, ou seja, é um método de `BuildRegistry`. Se não for, parar e reportar NEEDS_CONTEXT.

- [ ] **Step 2: Escrever `build_mode.py`**

```python
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

    @property
    def build_name(self) -> Optional[str]:
        return self._build.build_name if self._build is not None else None

    @property
    def busy(self) -> bool:
        return self._pending or self._pass is not None

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

    def advance(self) -> Optional[BuildPassOutcome]:
        """Call once per frame. Returns an outcome when a pass finishes, else None."""
        if self._pass is None:
            if not self._pending:
                return None
            self._pending = False
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
            self._pass.close()
        self._pass = None
        cast = self._build.last_cast if self._build is not None else None
        return BuildPassOutcome(cast=cast, error=error)
```

Notas para o implementador:
- `BarSignature = tuple[...]` é avaliado em tempo de execução; funciona em 3.9+.
- Se o Pyright reclamar dos tipos de `Agent.GetProfessions` ou `GetSkillIDBySlot`, ajustar só com conversões `int(...)`, sem `type: ignore`.
- O `close()` num gerador já terminado é seguro.

- [ ] **Step 3: Pyright**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 "Widgets/Automation/Helpers/AutoRota/auto_rota_src/build_mode.py"`
Expected: `0 errors`

- [ ] **Step 4: Os testes offline continuam a passar (o `__init__.py` não importa este módulo)**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 27 tests` … `OK`

- [ ] **Step 5: Commit**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/build_mode.py
git commit -m "feat(auto-rota): build mode detection and controlled build pass

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Alterações ao `game_adapter.py`

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`

- [ ] **Step 1: Imports**

Juntar (um por linha, por ordem):
- `from typing import Sequence` ao lado de `from typing import Optional`;
- `from .priorities import Tier` ao lado de `from .priorities import HEALING_ATTRIBUTE_NAMES`.

- [ ] **Step 2: Máscara de skills no `_sync_combat`**

Substituir `_sync_combat` por:

```python
    def _sync_combat(self, blocked_skill_ids: Sequence[int] = ()) -> CombatClass:
        """Rebuild the private CombatClass from the live skillbar right before a decision."""
        combat = self._combat
        combat.Update(self._cached_data)
        combat.PrioritizeSkills()
        combat.ApplyBlockedSkillIDs(list(blocked_skill_ids))
        combat.is_skill_enabled = [True] * MAX_SKILLS
        combat.is_targeting_enabled = True
        return combat
```

- [ ] **Step 3: `next_decision` com `max_tier`, mais os métodos novos**

Substituir `next_decision` por:

```python
    def next_decision(self, preview: bool = False) -> Optional[Decision]:
        self._sync_combat()
        interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview)

    def interrupt_decision(self, max_tier: Tier) -> Optional[Decision]:
        """Interrupt layer only (build mode): no rotation fallback, never reserves targets."""
        self._sync_combat()
        return choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible, max_tier=max_tier)

    def rotation_after_build(self, blocked_skill_ids: Sequence[int]) -> Optional[Decision]:
        """Rotation over the skills the build does not own (key-press path only)."""
        self._sync_combat(blocked_skill_ids)
        return self._rotation_decision(preview=False)

    def note_external_cast(self) -> None:
        """Start the debounce after a cast queued outside execute() (e.g. by a build pass)."""
        self._last_execute_s = time.monotonic()
```

(`next_decision` não muda de comportamento; fica igual, só para ficar ao lado dos novos métodos.)

- [ ] **Step 4: `describe` com o texto de "sem alvo" configurável**

Substituir `describe` por:

```python
    def describe(self, decision: Decision, no_target_text: str = "(alvo ao carregar)") -> str:
        if decision.target_id == 0:
            target_name = no_target_text
        else:
            target_name = Agent.GetNameByID(decision.target_id) or f"agente {decision.target_id}"
        text = f"{_skill_name(decision.skill_id)} -> {target_name}"
        if decision.enemy_skill_id:
            text += f" ({_skill_name(decision.enemy_skill_id)})"
        return f"{text} [{decision.label}]"
```

- [ ] **Step 5: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 "Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py"` → `0 errors`.
Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v` → `Ran 27 tests` … `OK`.
`awk 'length > 120'` no ficheiro → vazio.

- [ ] **Step 6: Commit**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py
git commit -m "feat(auto-rota): adapter hooks for build mode

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Integração no widget

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/Auto Rota.py`

- [ ] **Step 1: Imports e estado**

Imports a juntar (um por linha, por ordem, com os existentes de `Widgets.Automation...`):

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildMode
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildPassOutcome
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import BUILD_MODE_MAX_TIER
```

Estado global, logo a seguir a `_adapter = GameAdapter(_cached_data)`:

```python
_build_mode = BuildMode()
```

- [ ] **Step 2: Callback da tecla**

Substituir o corpo de `_on_hotkey` a partir de `reason = _adapter.blocker()` (mantendo os três filtros iniciais e o `except`) por:

```python
        if _build_mode.busy:
            _push_history(f"recusado: {REASON_BUSY}")
            return
        reason = _adapter.blocker()
        if reason is not None:
            _push_history(f"recusado: {reason}")
            return
        if _build_mode.build_name is None:
            decision = _adapter.next_decision()
            if decision is None:
                _push_history("nada a fazer")
                return
            _adapter.execute(decision)
            _push_history(_adapter.describe(decision))
            return
        interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER)
        if interrupt is not None:
            _adapter.execute(interrupt)
            _push_history(_adapter.describe(interrupt))
            return
        _build_mode.request_pass()  # the widget's main() drives the pass over the next frames
```

- [ ] **Step 3: Fim da passagem**

Nova função, a seguir a `_on_hotkey`:

```python
def _finish_build_pass(outcome: BuildPassOutcome) -> None:
    if outcome.error is not None:
        _push_history(f"erro: {outcome.error}")
        ConsoleLog(MODULE_NAME, f"build pass: {outcome.error}", Console.MessageType.Error)
        return
    if outcome.cast is not None:
        skill_id, target_id = outcome.cast
        _adapter.note_external_cast()
        label = f"Build: {_build_mode.build_name or '?'}"
        cast = Decision(bar_slot=0, skill_id=skill_id, target_id=target_id, label=label)
        _push_history(_adapter.describe(cast, no_target_text="(sem alvo)"))
        return
    decision = _adapter.rotation_after_build(_build_mode.blocked_skill_ids())
    if decision is None:
        _push_history("nada a fazer")
        return
    _adapter.execute(decision)
    _push_history(_adapter.describe(decision))
```

- [ ] **Step 4: Pré-visualização**

Substituir as duas últimas linhas de `_update_preview` (a partir de `decision = _adapter.next_decision(preview=True)`) por:

```python
    if _build_mode.build_name is None:
        decision = _adapter.next_decision(preview=True)
        _preview_text = _adapter.describe(decision) if decision is not None else "nada a fazer"
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER)
    _preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao carregar)"
```

Se a última linha passar de 120 caracteres, partir com parênteses:

```python
    _preview_text = (
        _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao carregar)"
    )
```

- [ ] **Step 5: Janela**

Em `_draw_window`, logo a seguir ao bloco do aviso vermelho e antes de `PyImGui.text(f"Proxima jogada: {_preview_text}")`:

```python
            build_name = _build_mode.build_name
            PyImGui.text(f"Build: {build_name}" if build_name else "Build: nenhuma (rotacao generica)")
```

- [ ] **Step 6: Tooltip**

Substituir as duas linhas `PyImGui.bullet_text(...)` do `tooltip()` por:

```python
    PyImGui.bullet_text("1. Interrupt por prioridade (ressurreicao, cura, elite, cast longo)")
    PyImGui.bullet_text("2. Senao, a jogada da build de Mesmer detetada, se houver")
    PyImGui.bullet_text("3. Senao, a proxima skill da rotacao do HeroAI")
```

- [ ] **Step 7: `main()`**

No `main()`, logo a seguir ao bloco `if not _hotkey_registered: ...` e antes do bloco da pré-visualização:

```python
        try:
            _build_mode.refresh()
        except Exception as exc:
            _log_error_once("build", exc)
        outcome = _build_mode.advance()
        if outcome is not None:
            _finish_build_pass(outcome)
```

- [ ] **Step 8: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 "Widgets/Automation/Helpers/AutoRota"` → `0 errors`.
Run: `python3.12 -m py_compile "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"` → sem output; apagar o `__pycache__` criado em `Widgets/Automation/Helpers/AutoRota/`.
`awk 'length > 120'` no widget → vazio.
Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v` → `Ran 27 tests` … `OK`.

- [ ] **Step 9: Commit**

```bash
git add "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"
git commit -m "feat(auto-rota): wire build mode into the widget

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Verificação offline e atualização da spec

**Files:**
- Modify: `docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md`
- Modify: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`

- [ ] **Step 1: Verificação completa**

```bash
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v
```

Expected: `Ran 27 tests` … `OK`

```bash
npx -y pyright@1.1.390 --pythonversion 3.13 "Widgets/Automation/Helpers/AutoRota" "Examples and tests/tests/auto_rota"
```

Expected: `0 errors`

```bash
git status --short
```

Expected: limpo, exceto os ficheiros de spec desta tarefa.

- [ ] **Step 2: Spec do modo build**

Na tabela de componentes, trocar a linha do `game_adapter.py` por:
`| auto_rota_src/game_adapter.py | interrupt_decision(max_tier), rotation_after_build(blocked_skill_ids), note_external_cast(); máscara de skills no _sync_combat; describe(decision, no_target_text) |`
e acrescentar, depois da secção "Comportamento ao carregar na tecla":
`O "ocupado" durante a passagem é verificado no widget (_build_mode.busy), antes do blocker() do adapter.`
Mudar o estado no topo para `Estado: implementado, por validar no jogo`.

- [ ] **Step 3: Spec base**

Em `2026-10-24-auto-rota-design.md`, na secção "Comportamento ao carregar na tecla", acrescentar no fim:
`Com uma build de Mesmer detetada, o comportamento muda conforme docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md.`

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md docs/superpowers/specs/2026-10-24-auto-rota-design.md
git commit -m "docs(auto-rota): build mode spec reflects implementation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Validação no jogo (manual, PC Windows)

Barra Energy Surge: Air of Superiority, Energy Surge, Ebon Vanguard Assassin Support e Cry of Frustration, mais Power Drain. Auto Rota ligada, Environment Upkeeper ligado, combate do HeroAI desligado.

- [ ] A janela mostra `Build: Energy Surge`.
- [ ] Um Monk inimigo a curar é interrompido pela Auto Rota: `[Interrupt: Cura]`.
- [ ] Um inimigo com um cast pouco importante: a Auto Rota não interrompe, e a build pode usar o Cry of Frustration (`[Build: Energy Surge]`).
- [ ] Sem casts inimigos, perto de inimigos: sai Energy Surge ou Air of Superiority (`[Build: Energy Surge]`).
- [ ] Uma skill fora da build só sai pela rotação (`[Rotacao]`), quando a build não tem nada para fazer.
- [ ] Carregar várias vezes depressa: no máximo uma skill por toque, e `recusado: ocupado` durante a passagem.
- [ ] Trocar uma skill obrigatória da build: a janela passa a `Build: nenhuma (rotacao generica)`.
- [ ] Na primeira vez que a build é detetada pode haver uma pequena pausa (importação das builds). Anotar se for notória.
