# Auto Rota — guarda contra hexes punitivos

Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
Depende de: `docs/superpowers/specs/2026-10-24-auto-rota-design.md` e
`docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md`

## Objetivo

Alguns hexes castigam quem os tem por fazer uma certa ação. Por exemplo, o
Backfire fere quem lança spells e o Empathy fere quem ataca. Com a Auto Rota
ligada, o ciclo automático continuaria a fazer essas ações e podia matar o
jogador.

A guarda resolve isso. Enquanto o jogador tiver em si um hex da lista, as
**jogadas automáticas** da Auto Rota não usam as skills que esse hex castiga.
Quando o hex acaba, as jogadas voltam ao normal sem nenhuma ação do jogador. Os
casts manuais nunca são bloqueados.

## Fora do âmbito

- **Remover o hex.** A guarda só pausa: não lança nem sugere skills de remoção.
  Quem remove é o jogador, à mão, ou os heróis (o HeroHelper já põe heróis a
  remover hexes perigosos do jogador).
- **Ataques normais (auto-attack).** A Auto Rota nunca ataca sem skill, mas o
  jogo pode continuar a atacar depois de uma skill de ataque. A guarda não
  consegue parar esses golpes (ver "Limites").
- **Lista editável pelo jogador.** A lista é fixa no código e testada offline.
- **Separar spells em inimigos de spells em aliados.** O jogo só castiga as
  spells em inimigos (Guilt, Mistrust) ou só as spells em aliados (Shame, Mark
  of Subversion). Mas a classificação de alvo do HeroAI não é fiável: uma skill
  sem dados conta como "Enemy". Por isso estes quatro bloqueiam todas as
  spells, no máximo 6 s.
- **Mudanças no BuildMgr, no CombatClass ou no HeroAI.**

## Catálogo

Os hexes ficam numa tabela pura `id -> (nome, ações castigadas)`, guardada pelo
**id** e não pelo nome. A razão: o `Skill.GetID(name)` é nativo, não corre
offline, e o repositório escreve alguns nomes de duas formas diferentes.

Os ids e os nomes foram verificados em `Py4GWCoreLib/skill_descriptions.json`.
As versões PvP são skills com o mesmo efeito e id próprio. Entram na tabela
porque não custam nada.

| Castiga | Hexes (id) |
|---|---|
| Spells | Backfire (28), Soul Leech (128), Arcane Languor (804), Mistrust (979, PvP 3191), Guilt (46), Shame (51), Mark of Subversion (127) |
| Ataques | Empathy (26, PvP 3151), Insidious Parasite (123), Spirit Shackles (66), Clumsiness (43), Ineptitude (47), Wandering Eye (2056, PvP 3195), Glimmering Mark (227) |
| Todas as skills | Spiteful Spirit (121), Visions of Regret (878, PvP 3234), Diversion (30), Panic (52) |
| Ataques e spells | Spoil Victor (1066, PvP 3233) |
| Shouts e chants | Cacophony (1998) |

São 25 ids no total.

### Proibidos

O Wastrel's Worry (50) e o Wastrel's Demise (1335) acabam quando o jogador usa
uma skill, por isso pausar fá-los fazer mais dano. Nunca podem entrar na
tabela, e há um teste que garante isso.

### Deixados de fora

Ficam de fora porque o custo é pequeno ou porque o castigo vem de ações de
outros:

- Power Leech (803)
- Depravity (820)
- Price of Pride (1655)
- Ulcerous Lungs (1358)
- Calculated Risk (2053, 3196)
- Price of Failure (103)
- Soul Barbs (100)
- Scourge Enchantment (1398)
- Scourge Healing (251)
- Soul Bind (901)
- Pain Inverter (2418)

## Classificação das skills da barra

Cada skill da barra recebe um `ActionKind`, a partir do tipo nativo
`GLOBAL_CACHE.Skill.GetType(skill_id)[0]` (`SkillType` em
`Py4GWCoreLib/enums_src/GameData_enums.py`):

| ActionKind | Tipos nativos |
|---|---|
| `SPELL` | Hex 4, Spell 5, Enchantment 6, Well 9, Ward 11, ItemSpell 24, WeaponSpell 25 (o mesmo conjunto que `_SPELL_TYPES`) |
| `ATTACK` | Attack 14 |
| `SHOUT_OR_CHANT` | Shout 15, Chant 27 |
| `OTHER` | todos os outros, incluindo signets, stances, glyphs, rituais, preparações, forms e ataques de pet |

Um hex de "todas as skills" castiga os quatro tipos. Os signets são `OTHER`.
Por isso, com o Backfire, os interrupts-signet continuam a sair.

## Leitura dos hexes no jogador

- **Uma leitura por frame:** `Effects.GetEffects(Player.GetAgentID())` (de
  `Py4GWCoreLib/Effect.py`), feita em `main()` antes da jogada e da
  pré-visualização. A leitura corre também com a Auto Rota desligada, para o
  aviso aparecer na mesma. Com a caixa "Guarda de hexes" desligada, não há
  leitura nem aviso.
- **Caminhos que não se usam:** a memória partilhada (`Routines.Checks.Agents.GetBuffs`
  e `HasEffect`) e o `GLOBAL_CACHE.Effects`. Dependem do multibox, misturam
  upkeeps e, no caso mais comum (hex ausente), custam várias cópias nativas por
  hex.
- **Filtro e duplicados:** ficam só os efeitos com id na tabela. Se o mesmo id
  aparecer mais de uma vez, conta o maior tempo restante.
- **Base no presente, não no tempo:** a guarda bloqueia enquanto o efeito
  existir.
- **Tempo mostrado:**
  - `time_remaining` está em milissegundos. Nove partes do código concordam
    nisso, mas falta confirmar no jogo.
  - `duration` está em segundos.
  - Um tempo é plausível quando `0 < restante <= duration * 1000 + 1000`.
  - Se não for plausível, o aviso mostra `?` e a guarda continua a bloquear.

## Regras

- **Skills bloqueadas:** os ids das skills da barra cujo `ActionKind` esteja na
  união das ações castigadas pelos hexes ativos. Com a guarda desligada, o
  conjunto é vazio.
- **Pausa da build:** a build fica em pausa quando o conjunto bloqueado
  partilha pelo menos um id com as skills da build
  (`BuildMode.blocked_skill_ids()`). Se o hex não tocar em nenhuma skill da
  build, ela continua igual.

## Ligação à Auto Rota

- **Decisões:** `GameAdapter.next_decision(preview, allow_buffs,
  blocked_skill_ids=())` e `GameAdapter.interrupt_decision(max_tier,
  blocked_skill_ids=())` passam os ids a `_sync_combat`.
  - `CombatClass.ApplyBlockedSkillIDs` **substitui** o conjunto de cada vez.
    Por isso, os ids bloqueados têm de ir em todas as chamadas, incluindo a
    pré-visualização.
  - Os interrupts e a rotação usam ambos `IsSkillReady`, que já rejeita os ids
    bloqueados, por isso as duas camadas ficam cobertas.
- **`_play_once`:**
  - **Sem build:** `next_decision(allow_buffs, blocked=guarda)`.
  - **Com build em pausa:** a jogada é a do modo sem build,
    `next_decision(allow_buffs, blocked=guarda)`, e não se pede a passagem.
  - **Com build não afetada:** como hoje, ou seja
    `interrupt_decision(BUILD_MODE_MAX_TIER, blocked=guarda)` e depois
    `request_pass()`.
- **`_finish_build_pass`:** `rotation_after_build(ids da build ∪ guarda)`.
- **Passagem em curso:** uma passagem da build que já começou não é cancelada,
  porque um cast já pedido ao jogo não se pode retirar. A jogada seguinte já
  respeita a guarda.
- **`_update_preview`:** segue a mesma lógica. Com a build em pausa, o texto é
  `build em pausa (<hex>): <jogada>`.

## Janela

- **Aviso:** a seguir à linha dos buffs, uma linha vermelha por hex ativo:
  `<nome> em ti: <ações> em pausa (<s> s)`, com o tempo arredondado para cima.
  - As `<ações>` são `spells`, `ataques`, `todas as skills`, `ataques e spells`
    ou `shouts e chants`.
  - Com um tempo não plausível, mostra `(? s)`.
- **Caixa "Guarda de hexes":** fica junto às teclas. Ligada por defeito e
  guardada em `Widgets/Config/auto_rota.ini` (secção `AutoRota`, chave
  `hex_guard`, booleana).
- **Histórico (só com a Auto Rota ligada):**
  - Quando um hex entra: `Guarda: <nome> - <ações> em pausa`.
  - Quando sai: `Guarda: <nome> acabou`.
- **Erro de leitura:** `Guarda: erro a ler efeitos (ver consola)` a vermelho.
  Nesse caso a guarda não bloqueia nada (falha aberta, a Auto Rota fica como
  antes) e o erro é registado uma vez na consola.
- **Tooltip:** uma linha nova, "Guarda de hexes: pausa as skills que um hex em
  ti castiga (ex.: Backfire -> spells)".

## Arquitetura

```
Widgets/Automation/Helpers/AutoRota/
├── Auto Rota.py                  # leitura por frame, aviso, caixa, histórico, ligação ao ciclo
└── auto_rota_src/
    ├── model.py                  # + ActionKind, ActiveHex(skill_id, remaining_ms: Optional[int]), BarSkill(skill_id, kind)
    ├── hex_guard.py              # NOVO, puro: PunishingHex, PUNISHING_HEXES e as regras
    └── game_adapter.py           # + punishing_hexes_on_player(), bar_skills(), _action_kind(); blocked_skill_ids nas decisões
Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py   # NOVO, unittest offline
```

Funções puras em `hex_guard.py` (sem Py4GWCoreLib):

- `active_punishing_hexes(effects: Iterable[tuple[int, int, float]]) -> tuple[ActiveHex, ...]`
  - Recebe tuplos `(skill_id, remaining_ms, duration_s)`.
  - Filtra pela tabela, junta os duplicados pelo maior tempo e marca como
    `None` o tempo não plausível.
- `guarded_skill_ids(bar: Sequence[BarSkill], hexes: Sequence[ActiveHex]) -> frozenset[int]`
- `build_paused_by_guard(guarded: frozenset[int], build_skill_ids: Iterable[int]) -> bool`
- `warning_text(hex: ActiveHex) -> str`: a linha vermelha da janela.
- `history_text(skill_id: int, started: bool) -> str`: a linha do histórico.
  O widget compara os ids ativos do frame anterior com os do frame atual e chama
  esta função para cada id que entrou ou saiu.

O `_action_kind(skill_id)` fica no `game_adapter.py`, ao lado de `_cast_kind`,
e usa `SkillType` e `_SPELL_TYPES`. Não pode ser testado offline, porque
importar os enums carrega o Py4GWCoreLib. A regra é verificada pelo Pyright e
no jogo.

## Testes offline

Os testes estão em `test_auto_rota_hex_guard.py` (unittest, `python3.12`) e
mostram a entrada e o resultado esperado e observado.

- **Tabela:** sem ids repetidos; sem 50 nem 1335; todas as entradas com pelo
  menos uma ação; os 25 ids do catálogo presentes.
- **`active_punishing_hexes`:** ignora ids fora da tabela; junta os duplicados
  pelo maior tempo; com `duration` 10 s e restante 4.29e9 ms dá `None`; com
  restante 0 dá `None`.
- **`guarded_skill_ids`:**
  - sem hex, nada bloqueado;
  - o Backfire bloqueia `SPELL` e não bloqueia `OTHER` (signet) nem `ATTACK`;
  - o Empathy bloqueia só `ATTACK`;
  - o Spiteful Spirit bloqueia tudo;
  - o Spoil Victor bloqueia `ATTACK` e `SPELL`;
  - o Cacophony bloqueia só `SHOUT_OR_CHANT`;
  - com dois hexes ativos, bloqueia a união;
  - slots vazios (id 0) nunca entram.
- **`build_paused_by_guard`:** pausa com interseção e não pausa sem ela.
- **Textos:** os segundos são arredondados para cima, e `?` aparece quando o
  tempo vem a `None`.

Os 35 testes da Auto Rota continuam a passar. O código alterado passa no
Pyright estrito (`--pythonplatform Windows`) e no Black a 120.

## Validação no jogo

1. **Backfire em ti:** as spells automáticas param e a linha vermelha conta
   para baixo cerca de 1 s por segundo. Isto confirma que o tempo vem em
   milissegundos.
2. **Fim do hex:** a Auto Rota volta a jogar sozinha e o histórico mostra
   `Guarda: Backfire acabou`.
3. **Empathy:** as skills de ataque param e as spells continuam.
4. **Build de Energy Surge com Backfire:** a pré-visualização mostra
   `build em pausa (Backfire)` e só saem jogadas que não são spells.
5. **Caixa desligada:** com a caixa "Guarda de hexes" desligada, nada é
   bloqueado.
6. **Ataques automáticos:** com Empathy, ver se o boneco continua a atacar
   sozinho depois de uma skill de ataque. Isso fica registado como limite.

## Limites e riscos

- **Ataques automáticos:** se o jogo continuar a atacar depois de uma skill de
  ataque, os hexes de ataque ainda castigam esses golpes. Num Mesmer pesa pouco.
- **Leitura dos efeitos:** que os hexes no jogador aparecem em `GetEffects` foi
  deduzido do código (HeroHelper, KeiranThackerayEOTN), não visto no jogo. Se
  não aparecerem, a guarda nunca dispara. A validação 1 confirma isso.
- **Unidade do tempo:** se `time_remaining` não estiver em milissegundos, só o
  número mostrado fica errado. O bloqueio depende de o efeito existir, não do
  tempo.
- **Custo por frame:** uma cópia nativa da lista de efeitos por frame. Parece
  pequeno, mas não foi medido.
