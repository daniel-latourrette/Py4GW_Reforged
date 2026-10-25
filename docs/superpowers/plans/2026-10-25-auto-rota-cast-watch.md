# Auto Rota — Vigia de casts inimigos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma janela própria mostra em tempo real os casts inimigos ao alcance (inimigo, skill, barra estimada, cor do escalão e interrupt que chega a tempo). Com o ciclo desligado, uma terceira tecla (F3) dispara uma vez o interrupt que a Auto Rota escolheria.

**Architecture:**
- **Núcleo puro:**
  - `decide.py` ganha `cast_rows` e `interrupt_from_rows`, que partilham com `choose_interrupt` a ordem, a regra do slot e a criação da `Decision`. Um teste de equivalência prova que o ciclo escolhe o mesmo de hoje.
  - Um módulo puro novo, `cast_watch.py`, calcula a barra estimada e o texto da coluna de interrupt.
  - `key_edge.py` ganha a regra de precedência das teclas.
- **`GameAdapter`:** procura os casts só até ao alcance de spell e lê-os uma vez por tick com `cast_watch()`. Essa leitura serve a pré-visualização, a lista e a tecla.
- **Widget:** desenha a janela própria e liga a tecla.

**Tech Stack:**
- Python 3.13 32 bits no jogo; os testes offline correm com `python3.12`.
- Py4GWCoreLib: `GLOBAL_CACHE`, `Agent`, `Player`, `ImGui.DrawTexture` e o `cast_observer` do HeroAI.
- PyImGui.
- `unittest`.
- Pyright: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows`.
- Black 120: `/tmp/claude-501/bv/bin/black -l 120 -S`.
- isort, com a configuração do repositório: `/private/tmp/claude-501/-Users-latourrette-Library-Application-Support-Claude-scratch-workspaces-49d8e2c2-9de2-440a-9235-e4cee5b6baeb-767a30bf-66a0-444c-a0b5-1a82626cfd89-scratch-2026-10-24-74fffe/414cdc62-7ecb-4cdd-a140-a5d6d12b8bcf/scratchpad/isortvenv/bin/isort --settings-path pyproject.toml --check-only`.

**Spec:** `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md`

**Commits:**
- Só com autorização explícita do utilizador, como manda a regra do repositório.
- Se forem autorizados, há um commit no fim de cada tarefa, no branch `feature/auto-rota`.
- Todas as mensagens terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Sem autorização, os passos de commit são saltados.

**Desvio da spec decidido aqui:**
- A spec previa `EnemyCast.elapsed_known: bool = True`. Fica antes `EnemyCast.elapsed_ms: Optional[int] = 0`, com o tempo decorrido que o `cast_observer` mediu, ou `None` quando ainda não viu o cast.
- O motivo: o `remaining_ms` já vem cortado em zero. Com ele, um cast que passou do tempo previsto nunca chegaria a mostrar `a terminar?`, porque a leitura é refeita a cada 100 ms.
- A spec é atualizada na Task 5.

**Regras a respeitar:**
- **Textos da interface:** em português e **sem acentos**, porque a fonte do ImGui não os tem.
- **Comentários no código:** em inglês.
- **Imports:** uma linha por nome (isort `force_single_line`).
- **Módulos testados offline:** `model.py`, `decide.py`, `cast_watch.py`, `key_edge.py` e `priorities.py` nunca importam Py4GWCoreLib.
- **`decide.py`:** já estava fora do formato do Black antes deste plano (commit 1a57dd27). Neste plano o ficheiro é alterado, e as partes novas têm de seguir o Black. O Black é verificado só nas linhas novas, comparando o número de diferenças antes e depois: são 1 hoje e têm de continuar a ser 1.

---

## Estrutura de ficheiros

| Ficheiro | Responsabilidade |
|---|---|
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py` | + `TIER_COLORS` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py` | + `EnemyCast.elapsed_ms`, + `CastRow` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py` | + `cast_rows`, `interrupt_from_rows`; `choose_interrupt` passa a usar os ajudantes partilhados |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/key_edge.py` | + `shadowed_positions` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py` | **Novo, puro.** `WATCH_MAX_ROWS`, `CastProgress`, `cast_progress`, `interrupt_text`, `WatchLabels` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py` | Alcance de spell, `elapsed_ms`, `cast_watch()`, `agent_name`, `skill_name`, `skill_icon_path`, `next_decision(rows=...)` |
| `Widgets/Automation/Helpers/AutoRota/Auto Rota.py` | Tecla interrupt, leitura única por tick, janela da vigia, caixa e tooltip |
| `Examples and tests/tests/auto_rota/test_auto_rota_decide.py` | + testes das linhas, da equivalência e da precedência de teclas |
| `Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py` | **Novo.** Testes da barra e do texto de interrupt |
| `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md` | Estado → implementado; nota do desvio |
| `docs/superpowers/specs/2026-10-24-auto-rota-design.md` | Linha "Ver também" |

---

### Task 1: Regra partilhada — linhas por cast e equivalência com `choose_interrupt` (TDD)

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py`
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py`
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py`
- Test: `Examples and tests/tests/auto_rota/test_auto_rota_decide.py`

- [ ] **Step 1: Escrever os testes (vão falhar)**

Em `Examples and tests/tests/auto_rota/test_auto_rota_decide.py`:

1. Substitui o import:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import can_hit  # noqa: E402
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import FeasibilityCheck  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import can_hit  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import cast_rows  # noqa: E402
```

2. Substitui o import:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import classify  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import is_eligible_build  # noqa: E402
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import classify  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import interrupt_from_rows  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import is_eligible_build  # noqa: E402
```

3. Substitui o import:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import next_auto_state  # noqa: E402
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import next_auto_state  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import shadowed_positions  # noqa: E402
```

4. Substitui o import:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import TIER_LABELS  # noqa: E402
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import TIER_COLORS  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import TIER_LABELS  # noqa: E402
```

5. Em `ClassifyTests`, a seguir a `test_every_tier_has_a_label`, acrescenta:

```python

    def test_every_tier_has_a_color(self) -> None:
        missing = set(Tier) - set(TIER_COLORS)
        self.assertEqual(missing, set(), f"TIER_COLORS is missing colors for tiers: {sorted(t.name for t in missing)}")
```

6. Imediatamente antes de `class BuildEligibilityTests(unittest.TestCase):`, acrescenta:

```python
def only_agent(agent_id: int) -> FeasibilityCheck:
    def check(_slot: InterruptSlot, cast: EnemyCast) -> bool:
        return cast.agent_id == agent_id

    return check


def not_agent(agent_id: int) -> FeasibilityCheck:
    def check(_slot: InterruptSlot, cast: EnemyCast) -> bool:
        return cast.agent_id != agent_id

    return check


def only_skill(skill_id: int) -> FeasibilityCheck:
    def check(slot: InterruptSlot, _cast: EnemyCast) -> bool:
        return slot.skill_id == skill_id

    return check


class CastRowsTests(unittest.TestCase):
    # The ChooseInterruptTests situations, so the list and the one-tap key provably pick what the loop picks.
    SCENARIOS: list[tuple[str, list[EnemyCast], list[InterruptSlot], FeasibilityCheck]] = [
        ("no casts", [], [make_slot()], always),
        ("no slots", [make_cast()], [], always),
        (
            "resurrection vs healing",
            [make_cast(agent_id=10, is_healing=True), make_cast(agent_id=20, is_resurrection=True)],
            [make_slot()],
            always,
        ),
        (
            "same tier, earlier finish",
            [
                make_cast(agent_id=10, is_healing=True, remaining_ms=900),
                make_cast(agent_id=20, is_healing=True, remaining_ms=400),
            ],
            [make_slot()],
            always,
        ),
        (
            "spell-only interrupt vs attack",
            [make_cast(agent_id=10, kind=CastKind.ATTACK, is_elite=True)],
            [make_slot(reach=InterruptReach.SPELL_OR_CHANT)],
            always,
        ),
        (
            "first feasible slot",
            [make_cast(agent_id=10)],
            [make_slot(slot=0, bar_slot=1, skill_id=501), make_slot(slot=1, bar_slot=2, skill_id=502)],
            only_skill(502),
        ),
        (
            "resurrection out of reach",
            [make_cast(agent_id=10, is_resurrection=True), make_cast(agent_id=20, is_elite=True)],
            [make_slot()],
            not_agent(10),
        ),
        (
            "tier outranks time",
            [
                make_cast(agent_id=10, is_healing=True, remaining_ms=200),
                make_cast(agent_id=20, is_resurrection=True, remaining_ms=1500),
            ],
            [make_slot()],
            always,
        ),
        (
            "exact tie",
            [make_cast(agent_id=10, is_elite=True), make_cast(agent_id=20, is_elite=True)],
            [make_slot()],
            always,
        ),
        (
            "long cast and infeasible healing",
            [make_cast(agent_id=10, activation_ms=3000), make_cast(agent_id=20, is_healing=True)],
            [make_slot()],
            not_agent(20),
        ),
        (
            "elite at the limit vs earlier other",
            [make_cast(agent_id=20, remaining_ms=100), make_cast(agent_id=10, is_elite=True, remaining_ms=900)],
            [make_slot()],
            always,
        ),
        (
            "every tier present",
            [
                make_cast(agent_id=50),
                make_cast(agent_id=40, activation_ms=2500),
                make_cast(agent_id=30, is_elite=True),
                make_cast(agent_id=20, is_healing=True),
                make_cast(agent_id=10, is_resurrection=True),
            ],
            [make_slot()],
            only_agent(40),
        ),
    ]

    def test_rows_give_the_same_decision_as_choose_interrupt_for_every_tier(self) -> None:
        for label, casts, slots, feasible in self.SCENARIOS:
            for max_tier in Tier:
                expected = choose_interrupt(casts, slots, feasible, max_tier=max_tier)
                observed = interrupt_from_rows(cast_rows(casts, slots, feasible), max_tier)
                self.assertEqual(
                    observed, expected, f"{label}, max_tier={max_tier.name}: expected={expected} observed={observed}"
                )

    def test_rows_keep_the_choice_order_and_casts_without_a_slot(self) -> None:
        casts = [
            make_cast(agent_id=30, remaining_ms=100),
            make_cast(agent_id=10, is_healing=True),
            make_cast(agent_id=20, kind=CastKind.ATTACK, is_resurrection=True),
        ]
        rows = cast_rows(casts, [make_slot(skill_id=501, reach=InterruptReach.SPELL)], always)
        observed = [(row.cast.agent_id, row.tier, row.slot.skill_id if row.slot else None) for row in rows]
        expected = [(20, Tier.RESURRECTION, None), (10, Tier.HEALING, 501), (30, Tier.OTHER, 501)]
        self.assertEqual(observed, expected, f"rows expected={expected} observed={observed}")

    def test_each_row_gets_its_first_feasible_slot(self) -> None:
        slots = [make_slot(slot=0, bar_slot=1, skill_id=501), make_slot(slot=1, bar_slot=2, skill_id=502)]

        def first_only_for_agent_10(slot: InterruptSlot, cast: EnemyCast) -> bool:
            return slot.skill_id == 502 or cast.agent_id == 10

        rows = cast_rows([make_cast(agent_id=10), make_cast(agent_id=20)], slots, first_only_for_agent_10)
        observed = [(row.cast.agent_id, row.slot.skill_id if row.slot else None) for row in rows]
        self.assertEqual(observed, [(10, 501), (20, 502)], f"slots per row observed={observed}")

    def test_rows_stop_at_the_tier_limit_like_choose_interrupt(self) -> None:
        rows = cast_rows([make_cast(agent_id=10, activation_ms=3000)], [make_slot()], always)
        observed = interrupt_from_rows(rows, Tier.ELITE)
        self.assertIsNone(observed, f"long cast above limit ELITE must not be picked, observed={observed}")
```

7. No fim de `KeyEdgeTests` (a seguir a `test_key_already_down_at_start_does_not_fire`), acrescenta:

```python


class ShadowedPositionsTests(unittest.TestCase):
    def check(self, indices: list[int], expected: set[int]) -> None:
        observed = shadowed_positions(indices)
        self.assertEqual(observed, frozenset(expected), f"indices={indices} expected={expected} observed={observed}")

    def test_distinct_keys_shadow_nothing(self) -> None:
        self.check([1, 2, 3], set())

    def test_a_later_position_loses_to_an_earlier_one(self) -> None:
        self.check([1, 1, 3], {1})
        self.check([1, 2, 2], {2})
        self.check([1, 2, 1], {2})

    def test_three_equal_keys_keep_only_the_first(self) -> None:
        self.check([3, 3, 3], {1, 2})
```

- [ ] **Step 2: Correr os testes e confirmar que falham**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: FAIL com `ImportError: cannot import name 'cast_rows'`.

- [ ] **Step 3: `TIER_COLORS` em `priorities.py`**

A seguir ao dicionário `TIER_LABELS` (antes de `LONG_CAST_MS = 2000`), acrescenta:

```python

# RGBA for the cast watch window (warm = must stop, grey = least important).
TIER_COLORS: dict[Tier, tuple[float, float, float, float]] = {
    Tier.RESURRECTION: (0.95, 0.40, 0.40, 1.0),
    Tier.HEALING: (1.00, 0.65, 0.25, 1.0),
    Tier.ELITE: (1.00, 0.84, 0.30, 1.0),
    Tier.LONG_CAST: (0.55, 0.75, 1.00, 1.0),
    Tier.OTHER: (0.55, 0.55, 0.55, 1.0),
}
```

- [ ] **Step 4: `EnemyCast.elapsed_ms` e `CastRow` em `model.py`**

1. Acrescenta a seguir a `from typing import Optional`:

```python

from .priorities import Tier
```

2. Em `EnemyCast`, substitui:

```python
    activation_ms: int
    remaining_ms: int
```

por:

```python
    activation_ms: int
    remaining_ms: int
    elapsed_ms: Optional[int] = 0  # what the cast observer measured; None = not seen yet (no progress reading)
```

3. Acrescenta no fim do ficheiro:

```python


@dataclass(frozen=True)
class CastRow:
    """One enemy cast in the interrupt choice order, with the first interrupt that lands on it (None: none in time)."""

    cast: EnemyCast
    tier: Tier
    slot: Optional[InterruptSlot]
```

- [ ] **Step 5: Ajudantes partilhados, `cast_rows` e `interrupt_from_rows` em `decide.py`**

1. Substitui o bloco de imports locais:

```python
from .model import BuildCandidate
from .model import CastKind
```

por:

```python
from .model import BuildCandidate
from .model import CastKind
from .model import CastRow
```

2. Substitui a função `choose_interrupt` inteira (de `def choose_interrupt(` até ao `return None` dela, antes de `def is_eligible_build`) por:

```python
def _first_slot(cast: EnemyCast, slots: Sequence[InterruptSlot], feasible: FeasibilityCheck) -> Optional[InterruptSlot]:
    """First slot, in the given (CombatClass priority) order, that can hit the cast and lands in time."""
    for slot in slots:
        if can_hit(slot.reach, cast.kind) and feasible(slot, cast):
            return slot
    return None


def _interrupt_decision(cast: EnemyCast, slot: InterruptSlot, tier: Tier) -> Decision:
    return Decision(
        bar_slot=slot.bar_slot,
        skill_id=slot.skill_id,
        target_id=cast.agent_id,
        label=f"Interrupt: {TIER_LABELS[tier]}",
        enemy_skill_id=cast.skill_id,
    )


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
        slot = _first_slot(cast, slots, feasible)
        if slot is not None:
            return _interrupt_decision(cast, slot, tier)
    return None


def cast_rows(casts: Sequence[EnemyCast], slots: Sequence[InterruptSlot], feasible: FeasibilityCheck) -> list[CastRow]:
    """Every cast in choose_interrupt's order, each with its first feasible slot (eager: the cast watch lists all)."""
    return [
        CastRow(cast=cast, tier=classify(cast), slot=_first_slot(cast, slots, feasible))
        for cast in sorted(casts, key=_cast_key)
    ]


def interrupt_from_rows(rows: Sequence[CastRow], max_tier: Tier = Tier.OTHER) -> Optional[Decision]:
    """The decision choose_interrupt makes, read from cast_rows output (same order, same slot rule)."""
    for row in rows:
        if row.tier > max_tier:
            break
        if row.slot is not None:
            return _interrupt_decision(row.cast, row.slot, row.tier)
    return None
```

- [ ] **Step 6: `shadowed_positions` em `key_edge.py`**

1. Acrescenta a seguir a `from __future__ import annotations`:

```python

from typing import Sequence
```

2. Acrescenta no fim do ficheiro:

```python


def shadowed_positions(indices: Sequence[int]) -> frozenset[int]:
    """Positions whose key is already taken by an earlier position (earlier positions win)."""
    seen: set[int] = set()
    shadowed: set[int] = set()
    for position, index in enumerate(indices):
        if index in seen:
            shadowed.add(position)
        seen.add(index)
    return frozenset(shadowed)
```

- [ ] **Step 7: Correr os testes**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 43 tests` … `OK`. Aos 35 de antes juntam-se 8: 1 de cores, 4 de linhas e 3 de precedência.

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v`
Expected: `Ran 26 tests` … `OK`.

- [ ] **Step 8: Pyright, Black e isort**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows Widgets/Automation/Helpers/AutoRota/auto_rota_src "Examples and tests/tests/auto_rota"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/key_edge.py "Examples and tests/tests/auto_rota/test_auto_rota_decide.py"`
Expected: `4 files would be left unchanged.`

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check --diff Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py | grep -c "^@@"`
Expected: `1`, a diferença que já existia em `is_eligible_build` e que fica de fora deste plano.

Run: `/private/tmp/claude-501/-Users-latourrette-Library-Application-Support-Claude-scratch-workspaces-49d8e2c2-9de2-440a-9235-e4cee5b6baeb-767a30bf-66a0-444c-a0b5-1a82626cfd89-scratch-2026-10-24-74fffe/414cdc62-7ecb-4cdd-a140-a5d6d12b8bcf/scratchpad/isortvenv/bin/isort --settings-path pyproject.toml --check-only` com os cinco ficheiros: `priorities.py`, `model.py`, `decide.py`, `key_edge.py` e `test_auto_rota_decide.py`.
Expected: sem output e código de saída 0.

Apaga os `__pycache__`:
Run: `find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests/auto_rota" -name __pycache__ -type d -prune -exec rm -rf {} +`

- [ ] **Step 9: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/priorities.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/decide.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/key_edge.py "Examples and tests/tests/auto_rota/test_auto_rota_decide.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): per-cast interrupt rows sharing choose_interrupt's rule, tier colors, key precedence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `cast_watch.py` — barra estimada e texto do interrupt (TDD)

**Files:**
- Create: `Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py`
- Create: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py`

- [ ] **Step 1: Escrever os testes (vão falhar)**

Cria `Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py` com:

```python
"""Offline unit tests for Auto Rota's cast watch helpers (no game runtime needed).

Run: python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import CastProgress  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import cast_progress  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import interrupt_text  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastKind  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastRow  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import EnemyCast  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptReach  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptSlot  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import Tier  # noqa: E402


def make_cast(activation_ms: int = 2000, elapsed_ms: Optional[int] = 1000) -> EnemyCast:
    seen_ms = elapsed_ms or 0
    return EnemyCast(
        agent_id=1,
        skill_id=100,
        kind=CastKind.SPELL,
        is_resurrection=False,
        is_healing=False,
        is_elite=False,
        activation_ms=activation_ms,
        remaining_ms=max(0, activation_ms - seen_ms),
        elapsed_ms=elapsed_ms,
    )


class CastProgressTests(unittest.TestCase):
    def check(self, cast: EnemyCast, seconds_since_read: float, expected: CastProgress) -> None:
        observed = cast_progress(cast, seconds_since_read)
        self.assertEqual(
            observed,
            expected,
            f"cast_progress(activation={cast.activation_ms}, elapsed={cast.elapsed_ms}, "
            f"since_read={seconds_since_read}) expected={expected} observed={observed}",
        )

    def test_a_cast_not_seen_yet_has_no_reading(self) -> None:
        self.check(make_cast(elapsed_ms=None), 0.0, CastProgress(fraction=None, label="?"))

    def test_an_instant_cast_has_no_reading(self) -> None:
        self.check(make_cast(activation_ms=0, elapsed_ms=0), 0.0, CastProgress(fraction=None, label="?"))

    def test_half_way_shows_the_seconds_left(self) -> None:
        self.check(make_cast(elapsed_ms=1000), 0.0, CastProgress(fraction=0.5, label="1.0s"))

    def test_the_bar_advances_between_reads(self) -> None:
        self.check(make_cast(elapsed_ms=1000), 0.5, CastProgress(fraction=0.75, label="0.5s"))

    def test_a_fresh_cast_starts_empty(self) -> None:
        self.check(make_cast(elapsed_ms=0), 0.0, CastProgress(fraction=0.0, label="2.0s"))

    def test_slightly_past_the_end_is_full_without_the_warning(self) -> None:
        self.check(make_cast(elapsed_ms=2300), 0.0, CastProgress(fraction=1.0, label="0.0s"))

    def test_well_past_the_end_says_it_may_be_finishing(self) -> None:
        self.check(make_cast(elapsed_ms=2301), 0.0, CastProgress(fraction=1.0, label="a terminar?"))
        self.check(make_cast(elapsed_ms=2000), 0.4, CastProgress(fraction=1.0, label="a terminar?"))


class InterruptTextTests(unittest.TestCase):
    def test_a_row_with_a_slot_names_the_interrupt(self) -> None:
        slot = InterruptSlot(slot=0, bar_slot=1, skill_id=500, reach=InterruptReach.ANY_CAST)
        row = CastRow(cast=make_cast(), tier=Tier.OTHER, slot=slot)
        observed = interrupt_text(row, "Cry of Frustration")
        self.assertEqual(observed, "a tempo: Cry of Frustration", f"observed={observed!r}")

    def test_a_row_without_a_slot_says_so(self) -> None:
        row = CastRow(cast=make_cast(), tier=Tier.OTHER, slot=None)
        observed = interrupt_text(row, "")
        self.assertEqual(observed, "sem interrupt a tempo", f"observed={observed!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Correr os testes e confirmar que falham**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch'`.

- [ ] **Step 3: Criar `cast_watch.py`**

Cria `Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py` com:

```python
"""Pure helpers for the cast watch window: the estimated cast-progress bar and the row texts.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import CastRow
from .model import EnemyCast

WATCH_MAX_ROWS = 6

# A cast seen running this long past its base activation is slowed or recast: say so instead of a stuck 100%.
_OVERRUN_GRACE_MS = 300


@dataclass(frozen=True)
class CastProgress:
    fraction: Optional[float]  # None: no reading (empty bar)
    label: str


@dataclass(frozen=True)
class WatchLabels:
    """Display strings for one row, captured at read time so names are not looked up every frame."""

    enemy: str
    skill: str
    icon_path: str
    interrupt: str


def cast_progress(cast: EnemyCast, seconds_since_read: float) -> CastProgress:
    """Estimated progress: base activation and the observer's first sighting, not the game's own clock.

    Enemy Fast Casting and slowing hexes are not modelled, so this is an estimate.
    """
    if cast.elapsed_ms is None or cast.activation_ms <= 0:
        return CastProgress(fraction=None, label="?")
    elapsed_ms = cast.elapsed_ms + seconds_since_read * 1000.0
    if elapsed_ms > cast.activation_ms + _OVERRUN_GRACE_MS:
        return CastProgress(fraction=1.0, label="a terminar?")
    fraction = min(1.0, max(0.0, elapsed_ms / cast.activation_ms))
    left_s = max(0.0, cast.activation_ms - elapsed_ms) / 1000.0
    return CastProgress(fraction=fraction, label=f"{left_s:.1f}s")


def interrupt_text(row: CastRow, skill_name: str) -> str:
    return f"a tempo: {skill_name}" if row.slot is not None else "sem interrupt a tempo"
```

- [ ] **Step 4: Correr os testes**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v`
Expected: `Ran 9 tests` … `OK`.

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 43 tests` … `OK`.

- [ ] **Step 5: Pyright, Black e isort**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py"`
Expected: `2 files would be left unchanged.`

Run: o isort em modo `--check-only` sobre os mesmos dois ficheiros.
Expected: código de saída 0.

Apaga os `__pycache__`, como na Task 1, Step 8.

- [ ] **Step 6: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/cast_watch.py "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): cast watch helpers (estimated cast progress, row texts)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `GameAdapter` — alcance de spell, tempo decorrido, `cast_watch()` e nomes

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`

Contexto:
- `is_interrupt_feasible` (`Py4GWCoreLib/HeroAI/interrupt.py`, na secção "Range gate") recusa qualquer alvo mais longe do que o alcance de spell, ou do que 144 nos interrupts corpo a corpo.
- Por isso, procurar casts só até ao alcance de spell não muda nenhuma escolha do ciclo.

- [ ] **Step 1: Imports**

1. Substitui:

```python
from .decide import choose_interrupt
```

por:

```python
from .decide import cast_rows
from .decide import choose_interrupt
from .decide import interrupt_from_rows
```

2. Substitui:

```python
from .model import CastKind
from .model import Decision
```

por:

```python
from .model import CastKind
from .model import CastRow
from .model import Decision
```

- [ ] **Step 2: Procurar casts só até ao alcance de spell**

Substitui:

```python
                if Utils.Distance(player_xy, Agent.GetXY(agent_id)) > Range.Longbow.value:
                    continue
```

por:

```python
                # Spellcast is the widest reach of any interrupt: is_interrupt_feasible's range gate truncates the
                # distance to int and rejects anything farther. Mirror it exactly, so farther casts (never chosen)
                # are skipped and the cast watch lists exactly the casts the loop considers.
                if int(Utils.Distance(player_xy, Agent.GetXY(agent_id))) > Range.Spellcast.value:
                    continue
```

- [ ] **Step 3: Guardar o tempo decorrido medido**

Em `_describe_cast`:

1. Substitui:

```python
        elapsed_ms = cast_observer.elapsed_ms(agent_id, skill_id) or 0
```

por:

```python
        observed_ms = cast_observer.elapsed_ms(agent_id, skill_id)  # None until the observer has seen the cast
        elapsed_ms = observed_ms or 0
```

2. Substitui:

```python
            remaining_ms=max(0, activation_ms - elapsed_ms),
        )
```

por:

```python
            remaining_ms=max(0, activation_ms - elapsed_ms),
            elapsed_ms=observed_ms,
        )
```

- [ ] **Step 4: `next_decision` aceita as linhas já lidas**

Substitui:

```python
    def next_decision(
        self, preview: bool = False, allow_buffs: bool = True, blocked_skill_ids: Iterable[int] = ()
    ) -> Optional[Decision]:
        # Blocked ids (the hex guard) must be passed on every call, the preview included:
        # ApplyBlockedSkillIDs replaces the set, so an omitted argument unblocks everything.
        self._sync_combat(blocked_skill_ids)
        interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview, allow_buffs)
```

por:

```python
    def next_decision(
        self,
        preview: bool = False,
        allow_buffs: bool = True,
        blocked_skill_ids: Iterable[int] = (),
        rows: Optional[Sequence[CastRow]] = None,
    ) -> Optional[Decision]:
        # Blocked ids (the hex guard) must be passed on every call, the preview included:
        # ApplyBlockedSkillIDs replaces the set, so an omitted argument unblocks everything.
        self._sync_combat(blocked_skill_ids)
        if rows is None:
            interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        else:
            interrupt = interrupt_from_rows(rows)  # rows from cast_watch() with the same blocked ids: no rescan
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview, allow_buffs)
```

- [ ] **Step 5: `cast_watch()` e os ajudantes de nomes**

A seguir ao método `bar_skills` (antes de `note_external_cast`), acrescenta:

```python
    def cast_watch(self, blocked_skill_ids: Iterable[int] = ()) -> list[CastRow]:
        """Every enemy cast in range with the interrupt that lands on it, read once (preview, list and key)."""
        self._sync_combat(blocked_skill_ids)
        return cast_rows(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)

    @staticmethod
    def agent_name(agent_id: int) -> str:
        return Agent.GetNameByID(agent_id) or f"agente {agent_id}"  # names decode asynchronously

    @staticmethod
    def skill_name(skill_id: int) -> str:
        return _skill_name(skill_id)

    @staticmethod
    def skill_icon_path(skill_id: int) -> str:
        """Relative icon path for ImGui.DrawTexture, or "" when the skill has no icon."""
        return GLOBAL_CACHE.Skill.ExtraData.GetTexturePath(skill_id)
```

- [ ] **Step 6: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: o Black em modo `--check` sobre `game_adapter.py`.
Expected: `1 file would be left unchanged.`

Run: o isort em modo `--check-only` sobre `game_adapter.py`.
Expected: código de saída 0.

Corre os três ficheiros de testes da Auto Rota (decide, hex guard e cast watch).
Expected: 43, 26 e 9 testes, todos OK.

Apaga os `__pycache__`.

- [ ] **Step 7: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py
git commit -m "$(cat <<'EOF'
feat(auto-rota): cast_watch() reads every cast in spell range once, with measured elapsed time

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Widget — tecla de um toque, leitura única por tick e janela da vigia

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/Auto Rota.py`

- [ ] **Step 1: Imports**

1. Substitui:

```python
from Py4GWCoreLib import Player
```

por:

```python
from Py4GWCoreLib import Agent
from Py4GWCoreLib import ImGui
from Py4GWCoreLib import Player
```

2. Substitui:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import SuggestedBuild
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import SuggestedBuild
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import WATCH_MAX_ROWS
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import WatchLabels
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import cast_progress
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import interrupt_text
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import interrupt_from_rows
```

3. Substitui:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import next_auto_state
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActiveHex
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import BUILD_MODE_MAX_TIER
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import next_auto_state
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import shadowed_positions
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActiveHex
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastRow
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import BUILD_MODE_MAX_TIER
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import TIER_COLORS
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import Tier
```

- [ ] **Step 2: Constantes e estado**

1. Substitui:

```python
_SETTINGS_HEX_GUARD = "hex_guard"
```

por:

```python
_SETTINGS_HEX_GUARD = "hex_guard"
_SETTINGS_INTERRUPT_HOTKEY = "interrupt_hotkey"
_SETTINGS_CAST_WATCH_OPEN = "cast_watch_open"
_WATCH_WINDOW = "Auto Rota: casts##auto_rota_casts"
_WATCH_ROW_H = 22.0
_WATCH_ICON = 20.0
_WATCH_BAR_W = 90.0
_WATCH_COLUMNS: tuple[tuple[str, float], ...] = (
    ("Inimigo", 130.0),
    ("##icon", _WATCH_ICON),
    ("Skill", 120.0),
    ("Cast", _WATCH_BAR_W),
    ("Interrupt", 120.0),
)
_TRACK_COLOR = (0.20, 0.20, 0.20, 1.0)
```

2. Substitui:

```python
_guard_error = False
```

por:

```python
_guard_error = False
_interrupt_key_index = 3  # F3 until the settings are loaded
_interrupt_key_edge = KeyEdge()
_watch_open = True  # loaded from the settings together with the keys
_watch_rows: list[CastRow] = []
_watch_labels: list[WatchLabels] = []
_watch_read_s = 0.0
_watch_key_target = 0  # agent the one-tap key would interrupt now (0: none)
_watch_key_text = ""
_watch_paused = ""  # stop reason while the Auto Rota cannot play
_watch_error = False
```

- [ ] **Step 3: Guardar a leitura e a tecla de um toque**

A seguir à função `_on_toggle_press` (antes de `_play_once`), acrescenta:

```python
def _store_watch(rows: list[CastRow]) -> None:
    """Keep one read for the cast watch: rows, display strings and what the one-tap key would fire."""
    global _watch_rows, _watch_labels, _watch_read_s, _watch_key_target, _watch_key_text
    labels: list[WatchLabels] = []
    for row in rows[:WATCH_MAX_ROWS]:
        slot_name = _adapter.skill_name(row.slot.skill_id) if row.slot is not None else ""
        labels.append(
            WatchLabels(
                enemy=_adapter.agent_name(row.cast.agent_id),
                skill=_adapter.skill_name(row.cast.skill_id),
                icon_path=_adapter.skill_icon_path(row.cast.skill_id),
                interrupt=interrupt_text(row, slot_name),
            )
        )
    decision = interrupt_from_rows(rows, Tier.OTHER)
    _watch_rows, _watch_labels, _watch_read_s = rows, labels, time.monotonic()
    _watch_key_target = decision.target_id if decision is not None else 0
    _watch_key_text = _adapter.describe(decision) if decision is not None else ""


def _on_interrupt_press() -> None:
    if not _press_allowed():
        return
    if _auto_on:
        _ignore_press("ciclo ligado: a tecla de interrupt so funciona com ele desligado")
        return
    reason = REASON_BUSY if _build_mode.busy else _adapter.blocker()
    if reason is not None:
        _ignore_press(f"interrupt: {reason}")
        return
    rows = _adapter.cast_watch(_guard_ids)  # fresh read: whether an interrupt lands depends on the instant
    _store_watch(rows)
    # All tiers, also with a detected build: the build-mode limit defers to the build's own logic,
    # which only runs while the loop is on.
    decision = interrupt_from_rows(rows, Tier.OTHER)
    if decision is None:
        _ignore_press("nenhum interrupt pronto chega a tempo" if rows else "sem casts inimigos ao alcance")
        return
    _adapter.execute(decision)
    _push_history(f"1 toque: {_adapter.describe(decision)}")
```

- [ ] **Step 4: `_update_preview` usa uma só leitura**

Substitui a função `_update_preview` inteira por:

```python
def _update_preview() -> None:
    global _preview_text, _heroai_conflict, _watch_paused, _watch_error
    _heroai_conflict = _adapter.heroai_conflict()
    reason = _adapter.blocker()
    if reason is not None and reason != REASON_BUSY:
        _preview_text = f"em pausa ({reason})"
        _watch_paused = reason
        _store_watch([])
        return
    _watch_paused = ""
    rows: Optional[list[CastRow]] = None
    try:
        rows = _adapter.cast_watch(_guard_ids)  # one read per tick feeds the preview and the cast watch
        _watch_error = False
    except Exception as exc:
        _watch_error = True
        _log_error_once("cast watch", exc)
    _store_watch(rows or [])
    build_ids = _build_mode.blocked_skill_ids()
    build_paused = _build_mode.build_name is not None and build_paused_by_guard(_guard_ids, build_ids)
    if _build_mode.build_name is None or build_paused:
        decision = _adapter.next_decision(preview=True, allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids, rows=rows)
        text = _adapter.describe(decision) if decision is not None else "nada a fazer"
        _preview_text = f"build em pausa ({guard_reason(_guard_hexes)}): {text}" if build_paused else text
        return
    if rows is not None:
        interrupt = interrupt_from_rows(rows, BUILD_MODE_MAX_TIER)
    else:
        interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    _preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao jogar)"
```

- [ ] **Step 5: Janela da vigia**

A seguir à função `_update_preview` (antes de `_draw_window`), acrescenta:

```python
def _set_watch_open(open_: bool) -> None:
    global _watch_open
    _watch_open = open_
    _settings.set_bool(_SETTINGS_SECTION, _SETTINGS_CAST_WATCH_OPEN, open_)


def _draw_cast_table() -> int:
    """Draw the cast rows; return the agent id of a clicked row (0: none)."""
    flags = int(
        PyImGui.TableFlags.RowBg
        | PyImGui.TableFlags.BordersInnerV
        | PyImGui.TableFlags.SizingFixedFit
        | PyImGui.TableFlags.NoSavedSettings
    )
    if not PyImGui.begin_table("auto_rota_casts_table", 5, flags):
        return 0
    clicked = 0
    try:
        fixed = int(PyImGui.TableColumnFlags.WidthFixed)
        for name, width in _WATCH_COLUMNS:
            PyImGui.table_setup_column(name, fixed, width)
        PyImGui.table_headers_row()
        target_id = int(Player.GetTargetID() or 0)
        seconds_since_read = time.monotonic() - _watch_read_s
        for row, labels in zip(_watch_rows, _watch_labels):
            agent_id = row.cast.agent_id
            color = TIER_COLORS[row.tier]
            PyImGui.table_next_row(0, _WATCH_ROW_H)
            PyImGui.table_next_column()
            marker = "> " if agent_id == _watch_key_target else ""
            # "###": the ID depends on the agent only, so a click survives the marker or the name changing mid-press.
            label = f"{marker}{labels.enemy}###auto_rota_cast_{agent_id}"
            span = int(PyImGui.SelectableFlags.SpanAllColumns)
            if PyImGui.selectable(label, agent_id == target_id, span, (0.0, _WATCH_ROW_H)):
                clicked = agent_id
            PyImGui.table_next_column()
            if labels.icon_path:
                ImGui.DrawTexture(labels.icon_path, _WATCH_ICON, _WATCH_ICON)
            else:
                PyImGui.text("?")
            PyImGui.table_next_column()
            PyImGui.text_colored(labels.skill, color)
            PyImGui.table_next_column()
            progress = cast_progress(row.cast, seconds_since_read)
            PyImGui.push_style_color(int(PyImGui.ImGuiCol.PlotHistogram), color)
            PyImGui.push_style_color(int(PyImGui.ImGuiCol.FrameBg), _TRACK_COLOR)
            try:
                # Fixed width: AlwaysAutoResize collapses a -1 (fill) progress bar to nothing.
                PyImGui.progress_bar(progress.fraction or 0.0, _WATCH_BAR_W, 0.0, progress.label)
            finally:
                PyImGui.pop_style_color(2)
            PyImGui.table_next_column()
            if row.slot is not None:
                PyImGui.text_colored(labels.interrupt, _ON_COLOR)
            else:
                PyImGui.text_disabled(labels.interrupt)
        hidden = len(_watch_rows) - len(_watch_labels)
        if hidden > 0:
            PyImGui.table_next_row(0, _WATCH_ROW_H)
            PyImGui.table_next_column()
            PyImGui.text_disabled(f"+{hidden} casts")
    finally:
        PyImGui.end_table()
    return clicked


def _watch_size() -> tuple[float, float]:
    """List size from the live style: header, WATCH_MAX_ROWS rows and "+N casts", fixed per theme (never jumps)."""
    style = PyImGui.get_style()
    line_h = PyImGui.get_text_line_height()
    cell_x, cell_y = style.CellPadding
    pad_x, pad_y = style.WindowPadding
    # A table row is its tallest cell plus CellPadding.y above and below; the progress bar is a framed widget.
    row_h = max(_WATCH_ROW_H, line_h + 2.0 * style.FramePadding[1]) + 2.0 * cell_y
    header_h = line_h + 2.0 * cell_y
    height = header_h + (WATCH_MAX_ROWS + 1) * row_h + 2.0 * pad_y + 2.0
    columns_w = sum(column_w for _, column_w in _WATCH_COLUMNS)
    width = columns_w + len(_WATCH_COLUMNS) * (2.0 * cell_x + 1.0) + 2.0 * pad_x
    return (width, height)


def _draw_cast_watch_body() -> int:
    """Header line and the fixed-size list; return the agent id of a clicked row (0: none)."""
    key_label = _KEY_CHOICES[_interrupt_key_index][0]
    if _watch_key_text:
        PyImGui.text_colored(f"Interrupt ({key_label}): {_watch_key_text}", _ON_COLOR)
    else:
        PyImGui.text_disabled("sem interrupt viavel")
    if _auto_on:
        PyImGui.text_disabled("tecla em pausa: o ciclo esta ligado")
    clicked = 0
    PyImGui.begin_child("##auto_rota_casts_list", _watch_size(), True, 0)
    try:
        if _watch_paused:
            PyImGui.text_disabled(f"em pausa ({_watch_paused})")
        elif _watch_error:
            PyImGui.text_colored("erro (ver consola)", _WARNING_COLOR)
        elif not _watch_rows:
            PyImGui.text_disabled("nenhum inimigo a fazer cast")
        else:
            clicked = _draw_cast_table()
    finally:
        PyImGui.end_child()
    return clicked


def _draw_cast_watch() -> None:
    if not _watch_open:
        return
    flags = int(PyImGui.WindowFlags.AlwaysAutoResize | PyImGui.WindowFlags.NoCollapse)
    visible, still_open = PyImGui.begin_with_close(_WATCH_WINDOW, True, flags)
    clicked = 0
    try:
        if visible:
            clicked = _draw_cast_watch_body()
    finally:
        PyImGui.end()
    if not still_open:
        _set_watch_open(False)
    if clicked and Agent.IsValid(clicked):
        Player.ChangeTarget(clicked)  # a click only selects; the one-tap key fires
```

- [ ] **Step 6: Janela principal — terceira tecla, avisos e caixa**

1. Substitui:

```python
    global _key_index, _key_edge, _buff_key_index, _buff_key_edge, _guard_on
```

por:

```python
    global _key_index, _key_edge, _buff_key_index, _buff_key_edge, _guard_on
    global _interrupt_key_index, _interrupt_key_edge
```

2. Substitui:

```python
            if _buff_key_index == _key_index:
                PyImGui.text_colored("As duas teclas sao iguais: a tecla dos buffs e ignorada", _WARNING_COLOR)
```

por:

```python
            new_interrupt_index = PyImGui.combo("Tecla interrupt", _interrupt_key_index, labels)
            if new_interrupt_index != _interrupt_key_index:
                _interrupt_key_index = new_interrupt_index
                _settings.set_str(
                    _SETTINGS_SECTION, _SETTINGS_INTERRUPT_HOTKEY, _KEY_CHOICES[new_interrupt_index][1].name
                )
                _interrupt_key_edge = KeyEdge()
            shadowed = shadowed_positions((_key_index, _buff_key_index, _interrupt_key_index))
            if 1 in shadowed:
                PyImGui.text_colored("Tecla dos buffs igual a outra: e ignorada", _WARNING_COLOR)
            if 2 in shadowed:
                PyImGui.text_colored("Tecla interrupt igual a outra: e ignorada", _WARNING_COLOR)
```

3. Substitui:

```python
                _push_history("Guarda de hexes LIGADA" if new_guard_on else "Guarda de hexes DESLIGADA")
```

por:

```python
                _push_history("Guarda de hexes LIGADA" if new_guard_on else "Guarda de hexes DESLIGADA")
            new_watch_open = PyImGui.checkbox("Vigia de casts", _watch_open)
            if new_watch_open != _watch_open:
                _set_watch_open(new_watch_open)
```

- [ ] **Step 7: Tooltip**

Substitui:

```python
    PyImGui.text("Guarda de hexes: pausa as skills que um hex em ti castiga (ex.: Backfire -> spells).")
```

por:

```python
    PyImGui.text("Guarda de hexes: pausa as skills que um hex em ti castiga (ex.: Backfire -> spells).")
    PyImGui.text("Tecla interrupt (F3): com o ciclo desligado, interrompe uma vez o cast mais importante.")
    PyImGui.text("Vigia de casts: janela com os casts inimigos ao alcance e o interrupt que chega a tempo.")
```

- [ ] **Step 8: `main()` — carregar, ler a tecla e desenhar a janela**

1. Substitui:

```python
    global _key_index, _buff_key_index, _key_loaded, _main_tick_s, _preview_text, _guard_on
```

por:

```python
    global _key_index, _buff_key_index, _key_loaded, _main_tick_s, _preview_text, _guard_on
    global _interrupt_key_index, _watch_open
```

2. Substitui:

```python
            _guard_on = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, True)
            _key_loaded = True
```

por:

```python
            _guard_on = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, True)
            _interrupt_key_index = _load_key_index(_SETTINGS_INTERRUPT_HOTKEY, Key.VK_F3)
            _watch_open = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_CAST_WATCH_OPEN, True)
            _key_loaded = True
```

3. Substitui:

```python
        buff_key_down = _buff_key_index != _key_index and _is_key_down(_KEY_CHOICES[_buff_key_index][1].value)
        if _buff_key_edge.update(buff_key_down):
            try:
                _on_buff_toggle_press()
            except Exception as exc:
                _push_history(f"erro: {exc}")
                _log_error("buff key press", exc)
```

por:

```python
        # Equal keys: the toggle wins over buffs, buffs win over the one-tap interrupt.
        shadowed = shadowed_positions((_key_index, _buff_key_index, _interrupt_key_index))
        buff_key_down = 1 not in shadowed and _is_key_down(_KEY_CHOICES[_buff_key_index][1].value)
        if _buff_key_edge.update(buff_key_down):
            try:
                _on_buff_toggle_press()
            except Exception as exc:
                _push_history(f"erro: {exc}")
                _log_error("buff key press", exc)
        interrupt_key_down = 2 not in shadowed and _is_key_down(_KEY_CHOICES[_interrupt_key_index][1].value)
        if _interrupt_key_edge.update(interrupt_key_down):
            try:
                _on_interrupt_press()
            except Exception as exc:
                _push_history(f"erro: {exc}")
                _log_error("interrupt key press", exc)
```

4. Substitui:

```python
        _draw_window()
    except Exception as exc:
        _log_error_once("main", exc)
```

por:

```python
        _draw_window()
        try:
            _draw_cast_watch()
        except Exception as exc:
            _log_error_once("cast watch window", exc)
    except Exception as exc:
        _log_error_once("main", exc)
```

- [ ] **Step 9: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: o Black em modo `--check` sobre `"Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`.
Expected: `1 file would be left unchanged.`

Run: o isort em modo `--check-only` sobre `"Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`.
Expected: código de saída 0.

Run: `python3.12 -B -m py_compile "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: sem output.

Corre os três ficheiros de testes da Auto Rota.
Expected: 43, 26 e 9 testes, todos OK.

Confirma que todas as decisões levam a guarda de hexes:
Run: `grep -n "_adapter\.\(next_decision\|interrupt_decision\|cast_watch\|rotation_after_build\)(" "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: 7 linhas.
- Todas as chamadas a `next_decision`, `interrupt_decision` e `cast_watch` levam `_guard_ids`.
- `rotation_after_build` leva `sorted(blocked)`.
- Distribuição das 7 linhas:
  - `cast_watch`: uma em `_on_interrupt_press` e uma em `_update_preview`;
  - `next_decision`: uma em `_play_once` e uma em `_update_preview`;
  - `interrupt_decision`: uma em `_play_once` e uma de reserva em `_update_preview`;
  - `rotation_after_build`: uma em `_finish_build_pass`.

Apaga os `__pycache__`.

- [ ] **Step 10: Commit (só com autorização)**

```bash
git add "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): cast watch window and one-tap interrupt key (F3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Documentação e verificação final

**Files:**
- Modify: `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md`
- Modify: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`

- [ ] **Step 1: Estado e desvio na spec da vigia**

Em `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md`:

1. Substitui:

```markdown
Data: 2026-10-25 · Estado: aprovado, por implementar · Branch: `feature/auto-rota`
```

por:

```markdown
Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
```

2. Substitui:

```markdown
- O `EnemyCast` ganha o campo `elapsed_known: bool = True`. O valor por defeito
  mantém válidos os testes e as chamadas que já existem.
```

por:

```markdown
- O `EnemyCast` ganha o campo `elapsed_ms: Optional[int] = 0`. Guarda o tempo
  decorrido medido pelo `cast_observer`, ou `None` quando o cast ainda não foi
  visto. O valor por defeito mantém válidos os testes e as chamadas que já
  existem.
  - Na implementação substituiu o `elapsed_known: bool` previsto. O
    `remaining_ms` vem cortado em zero, e só com o tempo real é possível mostrar
    `a terminar?`.
```

3. Substitui:

```markdown
- **Elapsed:** `_describe_cast` preenche `elapsed_known` com o resultado de
  `cast_observer.elapsed_ms(...)`: `True` quando não é `None`.
```

por:

```markdown
- **Elapsed:** `_describe_cast` preenche `elapsed_ms` com o resultado de
  `cast_observer.elapsed_ms(...)`, incluindo `None`.
```

4. Substitui:

```markdown
  - Quando o cast ainda não foi visto (`elapsed_known=False`), devolve
    `fraction=None` e `label="?"`. A barra fica vazia.
  - Quando `activation_ms <= 0`, devolve o mesmo.
  - Nos outros casos calcula
    `decorrido = activation_ms - remaining_ms + seconds_since_read * 1000`.
```

por:

```markdown
  - Quando o cast ainda não foi visto (`elapsed_ms=None`), devolve
    `fraction=None` e `label="?"`. A barra fica vazia.
  - Quando `activation_ms <= 0`, devolve o mesmo.
  - Nos outros casos calcula
    `decorrido = elapsed_ms + seconds_since_read * 1000`.
```

- [ ] **Step 2: Ligação a partir da spec base**

Em `docs/superpowers/specs/2026-10-24-auto-rota-design.md`, substitui:

```markdown
Ver também: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` (guarda contra hexes punitivos).
```

por:

```markdown
Ver também: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` (guarda contra hexes punitivos)
e `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md` (vigia de casts e interrupt de um toque).
```

- [ ] **Step 3: Verificação completa**

Run, um a um:

```bash
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v
python3.12 "Examples and tests/tests/combat_meter/test_combat_meter.py" -v
npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota" "Examples and tests/tests/auto_rota"
find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests" -name __pycache__ -type d -prune -exec rm -rf {} +
git status --short
```

Expected:
- **Testes:** 43, 26, 9 e 11, todos OK.
- **Pyright:** `0 errors`.
- **`git status`:** só os ficheiros deste plano. Com os commits autorizados, ficam só os dois `.md` desta tarefa e o plano.

- [ ] **Step 4: Commit (só com autorização)**

```bash
git add docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md docs/superpowers/specs/2026-10-24-auto-rota-design.md docs/superpowers/plans/2026-10-25-auto-rota-cast-watch.md
git commit -m "$(cat <<'EOF'
docs(auto-rota): cast watch spec, plan and status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

## Validação no jogo (depois da implementação, pelo utilizador no Windows)

Copia de novo a pasta `Widgets/Automation/Helpers/AutoRota` a partir do zip do branch. Depois confirma:

1. **Janela:** "Auto Rota: casts" abre e fecha pela caixa "Vigia de casts" e pelo X, e lembra-se do estado depois de reiniciar o widget.
2. **Lista:** com inimigos a fazer cast, as linhas aparecem pela ordem certa e com as cores certas. A barra anda durante o cast e mostra `?` enquanto o cast ainda não foi visto.
3. **Tecla:** com o ciclo desligado, a F3 interrompe o cast da linha marcada com `>` e regista `1 toque: ...`. Com o ciclo ligado, é ignorada e o motivo aparece em "Ultimo toque ignorado".
4. **Clique:** um clique numa linha seleciona esse inimigo.
5. **Estabilidade:** a janela não salta enquanto as linhas mudam. Com 7 ou mais inimigos a fazer cast, veem-se as 6 linhas e a linha "+N casts", sem barra de scroll.
6. **Custo:** sem quebras de frames com vários inimigos a fazer cast.
