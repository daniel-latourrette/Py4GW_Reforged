# Auto Rota — reserva de energia para interrupts

Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
Depende de: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`,
`docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md`,
`docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` e
`docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md`

## Objetivo

Hoje a rotação automática só verifica se tens energia para a skill que vai lançar.
Pode gastar a energia toda num hex e deixar-te sem energia para interromper uma
ressurreição logo a seguir.

A reserva guarda energia para os interrupts. Com a Auto Rota ligada, uma skill da
**rotação** não é lançada se, depois de a pagares, a energia ficar abaixo da
reserva. Os interrupts nunca são bloqueados, nem os do ciclo nem os da tecla F3,
e os casts manuais também não.

## Fora do âmbito

- **As jogadas da build.** O `BuildMgr` verifica a energia por conta própria
  (`HasEnoughEnergy`), e as builds já põem os interrupts primeiro. A reserva não
  mexe nas passagens da build nem no código partilhado. Ver "Modo build".
- **Prever a energia futura.** A reserva não conta com a regeneração, nem com o
  momento em que um interrupt volta, nem com o overcast.
- **Escolher o interrupt por cast.** A reserva guarda energia para um interrupt;
  não verifica se esse interrupt consegue apanhar um cast concreto (o Power
  Drain, por exemplo, só corta spells e chants).
- **Mudanças no HeroAI ou no `BuildMgr`.**

## Modos

O modo escolhe-se numa lista na janela da Auto Rota e fica guardado em
`Widgets/Config/auto_rota.ini`, na secção `AutoRota`.

| Modo | Reserva (antes do teto) |
|---|---|
| **Interrupt mais barato** (por defeito) | O menor custo real entre os interrupts da barra, prontos ou a recarregar. Sem interrupts na barra, é 0. |
| **Fixa** | O valor escolhido: 10 por defeito, de 0 a 25. |
| **Desligada** | 0. A Auto Rota fica como hoje. |

- **Que interrupts contam:** as skills da barra que a Auto Rota trata como
  interrupts, ou seja com `Nature` Interrupt e um alcance de interrupt conhecido
  (`_REACH_BY_ALLEGIANCE`).
  - Contam prontas ou a recarregar. Assim, depois de interromperes, a energia
    fica guardada para quando o interrupt voltar.
  - Contam também as que a guarda de hexes está a bloquear, porque a pausa dura
    segundos e a energia vai ser precisa quando o hex acabar.
  - Não há filtro de energia: uma lista que tirasse os interrupts que não se
    podem pagar levaria a reserva a 0 exatamente quando a energia está baixa.
- **Signets e skills de adrenalina:** custam 0 energia. Se forem o interrupt
  mais barato, a reserva fica a 0, e está certo, porque esse interrupt nunca
  precisa de energia.
- **Custo real:** `Routines.Checks.Skills.GetEnergyCostWithEffects`, mais a
  redução de Expertise quando existe. É exatamente o custo que a verificação de
  recursos da Auto Rota já usa. Inclui efeitos como o Primal Echoes, que faz os
  signets custarem 10.
- **Teto:** a reserva efetiva é `min(reserva, energia máxima / 2)`. Com a
  energia máxima desconhecida (0 ou menos), a reserva é 0.

## Regra por skill

Uma skill da rotação **gastaria a reserva**, e não é lançada, quando a primeira
condição aplicável da lista seguinte o diz, por esta ordem:

1. Reserva efetiva de 0 ou menos: não gasta.
2. A skill esvazia a barra toda (Ether Lord, id 41): gasta.
3. A skill está isenta: não gasta. As isentas são:
   - as de custo real 0 ou menos;
   - as que o HeroAI marca com `Nature` EnergyBuff (Ether Signet, por exemplo);
   - as que dão energia, numa lista explícita, porque o HeroAI as marca como
     ofensivas: Drain Enchantment (68), Energy Drain (79), Energy Tap (80) e
     Waste Not, Want Not (1995).
4. Barra cheia (energia atual igual ou acima da máxima): não gasta. Assim
   nenhuma skill fica presa para sempre quando custo + reserva > energia máxima.
5. Senão, gasta quando `energia atual − custo < reserva efetiva`.

Os ids foram verificados em `Py4GWCoreLib/skill_descriptions.json`. Nenhuma
destas skills tem versão PvP.

- **Energia desconhecida:** quando a leitura da energia falha (o
  `GetEnergyValues` do HeroAI devolve −1), a reserva não faz nada. A verificação
  de recursos da Auto Rota já recusa lançar nesse caso.
- **Ponto único de aplicação:** a regra entra em `_rotation_decision`, depois da
  verificação de que a skill está pronta (`IsSkillReady`) e dos filtros que não
  reservam alvo (alvo selecionado, tipo de alvo, fora de combate), e antes do
  `IsReadyToCast` e das procuras de alvo da pré-visualização.
  - A pré-visualização só culpa a reserva por uma skill que passou esses filtros
    e que se podia pagar sem a reserva.
  - As condições de cast verificadas depois, no `IsReadyToCast` (haver um aliado
    ferido, o efeito ainda não estar no alvo), não são conhecidas nesse ponto.
    Nesses casos raros, a pré-visualização pode nomear uma skill que não sairia
    de qualquer forma.
  - Mudar isso obrigava a mexer na ordem do HeroAI, que é partilhado.
  Esse ponto cobre:
  - as jogadas reais e a pré-visualização;
  - a rotação normal;
  - a rotação depois da build;
  - a rotação que corre quando a guarda de hexes pausa a build.

  Por ficar antes do `IsReadyToCast` e das procuras de alvo, uma skill saltada
  nunca chega a reservar um alvo para as outras contas.
- **Interrupts:** a camada de interrupts nunca passa por esse ponto, e a tecla F3
  também não. Os interrupts nunca são bloqueados.

## Modo build

As passagens da build continuam como hoje: a build já gere a energia e põe os
interrupts primeiro. A reserva aplica-se à rotação normal, à rotação que corre
depois de uma passagem da build e à rotação que corre quando a guarda de hexes
pausa a build. O tooltip explica isto: "Reserva de energia: so na rotacao (a
build gere a propria energia)".

## Janela

- **Linha da energia**, a seguir à linha dos buffs, na janela principal:
  - `Energia: 23/50 - reserva 10 (Cry of Frustration)` no modo do mais barato,
    com o interrupt que define a reserva;
  - `Energia: 23/50 - reserva 10 (fixa)` no modo fixo;
  - `Energia: 23/50 - reserva desligada` no modo desligado;
  - `Energia: 23/50 - reserva 0 (sem interrupts)` no modo do mais barato sem
    interrupts na barra;
  - `Energia: ?` quando a leitura falha;
  - `Energia: erro (ver consola)` quando a leitura lança uma exceção.

  Os números são arredondados para baixo na energia e para cima na reserva.
- **Aviso** `sem energia para interromper`, a vermelho (`_WARNING_COLOR`): aparece
  quando há pelo menos um interrupt pronto e a energia não chega para nenhum dos
  interrupts prontos. A janela "Auto Rota: casts" mostra o mesmo aviso por baixo
  da linha de topo.
- **Pré-visualização:**
  - quando a reserva saltou uma skill e nenhuma outra saiu:
    `rotacao em pausa: reserva para interrupt (<skill>)`;
  - quando outra skill saiu no lugar dela, acrescenta
    `(reserva: saltou <skill>)` ao texto da jogada.
- **Controlos**, junto à caixa "Guarda de hexes":
  - lista **"Reserva interrupt"** com `Interrupt mais barato`, `Fixa` e
    `Desligada`;
  - em modo `Fixa`, um `slider_int` **"Reserva fixa"** de 0 a 25. O valor é
    limitado a 0–25 também quando é escrito com Ctrl+clique.
  - As chaves no ini são `energy_reserve_mode` (`cheapest`, `fixed` ou `off`) e
    `energy_reserve_fixed` (inteiro).
  - Mudar o modo regista uma linha no histórico, como a guarda.

## Arquitetura

```
Widgets/Automation/Helpers/AutoRota/
├── Auto Rota.py                  # controlos, linha da energia, avisos, preview, tooltip
└── auto_rota_src/
    ├── energy_reserve.py         # NOVO, puro: ReserveMode, InterruptCost, EnergyStatus, reserva com teto, regra, ids, textos
    └── game_adapter.py           # energia e custo partilhados, custos dos interrupts, regra em _rotation_decision, energy_status()
Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py   # NOVO, unittest offline
```

### `energy_reserve.py` (puro, sem Py4GWCoreLib)

- `class ReserveMode(Enum)`, com os valores `CHEAPEST = "cheapest"`,
  `FIXED = "fixed"` e `OFF = "off"`. O valor é o texto guardado no ini.
- `RESERVE_FIXED_DEFAULT = 10` e `RESERVE_FIXED_MAX = 25`.
- `ENERGY_GAIN_SKILL_IDS = frozenset({68, 79, 80, 1995})` e
  `DRAINS_ALL_ENERGY_SKILL_IDS = frozenset({41})`.
- `effective_reserve(mode, fixed, interrupt_costs, maximum) -> float` aplica a
  tabela dos modos e o teto.
- `breaks_reserve(current, cost, reserve, maximum, skill_id, energy_buff) -> bool`
  aplica a regra por skill, pela ordem da secção "Regra por skill".
- `energy_line(status, reserve_skill_name) -> str` e os textos dos avisos e da
  pré-visualização.
- `mode_from_setting(text) -> ReserveMode` converte o texto do ini. Um valor
  desconhecido conta como `CHEAPEST`.
- `InterruptCost(skill_id, cost, ready)`, imutável: um interrupt da barra com o
  seu custo real e se está pronto.
- `cannot_interrupt(current, costs)` e
  `make_energy_status(current, maximum, mode, fixed, costs) -> EnergyStatus`.

O `ReserveMode` e o `EnergyStatus` ficam neste módulo e não em `model.py`: no
`model.py`, os dois módulos importar-se-iam um ao outro. É o mesmo padrão do
`hex_guard.py`, que guarda o seu próprio `PunishingHex`.

### `EnergyStatus`

Tipo novo, imutável:
`EnergyStatus(current: Optional[float], maximum: float, mode: ReserveMode,
reserve: float, reserve_skill_id: int, cannot_interrupt: bool)`.

- `reserve_skill_id` é o interrupt que define a reserva no modo do mais barato,
  ou 0. Em caso de empate no custo, fica o primeiro pela ordem de prioridade do
  `CombatClass`.
- `cannot_interrupt` corresponde ao aviso: há interrupts prontos e a energia
  não chega para nenhum.

### `game_adapter.py`

- **Funções partilhadas:** `_current_energy() -> Optional[float]` e
  `_energy_cost(skill_id) -> float`.
  - `_current_energy` devolve `GetEnergyValues × GetMaxEnergy`, ou `None` quando
    a leitura falha.
  - `_energy_cost` devolve o custo com efeitos e Expertise.
  - `_has_resources` passa a usar estas duas funções, com o mesmo resultado de
    hoje.
- **`_interrupt_costs() -> list[InterruptCost]`:** devolve
  `InterruptCost(skill_id, cost, ready)` para cada skill da barra que seja
  interrupt.
  - Lê os dados do `CombatClass`, sem filtro de energia nem de bloqueio.
  - "Pronta" quer dizer recarga a 0 e adrenaline suficiente.
- **`_rotation_decision`:** recebe a reserva (o modo e o valor fixo vêm pelas
  chamadas, como o `allow_buffs`). Calcula a energia e a reserva uma vez antes
  do ciclo, aplica `breaks_reserve` depois dos filtros de alvo e de fora de
  combate e antes do `IsReadyToCast`, e guarda a
  primeira skill saltada em `self.reserve_skip_skill_id`. Esse valor é reposto
  a 0 em `_sync_combat`. Os tipos devolvidos não mudam.
- **`next_decision` e `rotation_after_build`:** ganham os argumentos
  `reserve_mode` e `reserve_fixed`, com os valores por defeito `OFF` e 0, para os
  chamadores que já existem não mudarem.
- **`energy_status(mode, fixed) -> EnergyStatus`:** a leitura usada pela janela e
  pela pré-visualização.

## Testes offline

O ficheiro é `test_auto_rota_energy_reserve.py` (unittest, `python3.12`). As
mensagens de erro mostram as entradas, o esperado e o observado.

- **`effective_reserve`:**
  - cada modo;
  - o mais barato entre vários custos;
  - um signet (custo 0) leva a reserva a 0;
  - sem interrupts, a reserva é 0;
  - o teto de metade da energia máxima;
  - a energia máxima desconhecida dá 0.
- **`breaks_reserve`:** um caso por regra, e a ordem entre elas:
  - reserva 0;
  - Ether Lord, também com a barra cheia;
  - custo 0;
  - EnergyBuff;
  - cada id da lista de energia;
  - barra cheia;
  - os limites de `current − cost < reserve`, incluindo a igualdade, que não
    gasta.
- **`mode_from_setting`:** os três textos e um valor desconhecido.
- **Textos:** a linha da energia em cada modo, `Energia: ?` e o arredondamento.

Os testes já existentes da Auto Rota (decide, hex guard, cast watch) e do Combat
Meter continuam a passar. O código alterado passa no Pyright
(`--pythonplatform Windows`), no Black a 120 e no isort.

## Validação no jogo

1. **A linha da energia** mostra valores certos: com a barra cheia, a energia
   atual é igual à máxima. Isto confirma que o `GetEnergyValues` é uma fração da
   energia máxima.
2. **Energia baixa, modo do mais barato:** a pré-visualização mostra
   `rotacao em pausa: reserva para interrupt (...)`, e os interrupts continuam a
   sair, pelo ciclo e pela F3.
3. **O aviso** `sem energia para interromper` acende quando nenhum interrupt
   pronto se pode pagar, e apaga quando a energia volta.
4. **Modo `Fixa` a 25:** a rotação guarda mais energia. Em `Desligada`, comporta-se
   como hoje.
5. **Build Psychic Instability Wastrel's:** as jogadas da build não mudam.
6. **Ether Signet ou Energy Tap na barra:** continuam a sair com a energia baixa.

## Limites e riscos

- **O mais barato pode não servir:** o interrupt mais barato pode não apanhar o
  cast que interessa. Por exemplo, o Power Drain só corta spells e chants.
- **Regeneração baixa:** com +1 de regeneração e 40 de máximo, a rotação passa
  muito tempo à espera. É honesto, mas pode parecer lento. O modo `Desligada`
  existe para isso.
- **Build fora da reserva:** no modo build, as jogadas da build podem gastar a
  reserva. Foi uma escolha consciente.
- **Duas fontes de energia:** a reserva usa o espelho do HeroAI (memória
  partilhada), e o `BuildMgr` lê a energia diretamente do jogo. Um atraso de um
  frame entre as duas não foi medido.
- **Lista explícita:** a lista de skills que dão energia é fixa. Uma skill nova
  com essa função, que não esteja na lista, segue a regra normal.
