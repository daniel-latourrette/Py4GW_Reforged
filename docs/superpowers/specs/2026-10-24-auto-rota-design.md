# Auto Rota — assistente de combate semi-automático (Mesmer)

Data: 2026-10-24 · Estado: design aprovado · Branch: `feature/auto-rota`

## Objetivo

Um widget em que o jogador carrega numa tecla e o personagem executa a
**melhor jogada do momento**. Foco principal: interrupts de Mesmer, escolhidos
por prioridade. O resto da rotação vem da lógica de combate do HeroAI.

Cada toque na tecla faz **uma** jogada. O widget nunca age sozinho.

## Fora do âmbito

- Modo contínuo ou "manter premida" (já existe: é o HeroAI em modo combate).
- Fila de toques: se o personagem estiver ocupado, o toque é ignorado.
- Ataque automático com a arma quando não há skill útil.
- Builds específicas escritas à mão (formato `BuildMgr`).
- Outras profissões: a lógica não depende de Mesmer, mas só é desenhada e
  testada para Mesmer.

## Comportamento ao carregar na tecla

1. **Verificações.** Só atua se, ao mesmo tempo:
   - o mapa for explorable (não outpost);
   - o jogador estiver vivo;
   - o jogador não estiver a fazer cast nem dentro do aftercast da jogada anterior;
   - o combate do HeroAI estiver desligado para esta conta (ver "Conflito com o HeroAI").

   Se alguma falhar, não lança nada e regista o motivo no histórico
   (ex.: "ocupado", "em outpost").
2. **Interrupts.** Calcula a melhor oportunidade de interrupt (secção seguinte).
   Se existir, lança-a.
3. **Rotação.** Se não houver interrupt, pede ao `CombatClass` do HeroAI a
   primeira skill castável que **não** seja um interrupt (`FindCastableSkill`,
   ignorando slots com `SkillNature.Interrupt`) e lança-a com
   `GLOBAL_CACHE.SkillBar.UseSkill`.
4. **Nada a fazer.** Se não houver nenhuma das duas, não faz nada e regista
   "nada a fazer".

A Auto Rota lança a skill diretamente. Não chama `HandleCombat`, para não
herdar o ataque automático nem os locks de multibox.

## Escolha do interrupt

### Candidatos
- **Inimigos:** inimigos vivos que estão a fazer cast (`Agent.IsCasting`), com
  a skill dada por `Agent.GetCastingSkillID`.
- **Interrupts do jogador:** slots da barra cuja skill tem
  `custom_skill_data.Nature == SkillNature.Interrupt`, que estejam prontos
  (`CombatClass.IsSkillReady`) e com energia suficiente.

### Compatibilidade interrupt ↔ cast
Respeita o `TargetAllegiance` de cada interrupt nos dados do HeroAI:

| `TargetAllegiance` | Casts que pode interromper |
|---|---|
| `EnemyCasting` | qualquer cast |
| `EnemyCastingSpell` | só spells |
| `EnemyCastingSpellOrChant` | spells e chants |
| `EnemyAttacking` | só skills de ataque |

Para cada combinação compatível, o par só é válido se
`HeroAI.interrupt.is_interrupt_feasible(alvo, skill, fast_casting, ping)`
devolver `True`. Essa função já trata do alcance, do ping, do Fast Casting e
dos hexes que abrandam.

### Níveis de prioridade (do mais para o menos importante)
1. **Ressurreição:** a skill do inimigo tem `Nature == Resurrection` nos dados
   do HeroAI (`CustomSkillClass`), por exemplo Resurrection Signet, Rebirth ou
   Restore Life (17 skills marcadas hoje).
2. **Cura:** `Nature == Healing` nos dados do HeroAI **ou** atributo da skill
   igual a Healing Prayers, Protection Prayers ou Restoration Magic. O atributo
   apanha as skills de monstros que não constam dos dados.
3. **Elite:** `Skill.Flags.IsElite`.
4. **Cast longo:** ativação de 2 segundos ou mais.
5. **Resto.**

**Desempate dentro do mesmo nível:** fica o cast que termina mais cedo. Entre
vários interrupts possíveis para esse cast, usa o primeiro pela ordem da barra.

A tabela de níveis e as listas de atributos ficam num único ficheiro
(`priorities.py`), para serem fáceis de editar.

## Janela de pré-visualização

Uma janela ImGui pequena com:
- **Próxima jogada:** a decisão que seria tomada agora, recalculada no máximo a
  cada 100 ms (ex.: `Power Spike → Monk (Orison of Healing) [Cura]`).
- **Histórico:** as últimas 5 jogadas ou motivos de recusa, com a hora.
- **Tecla:** a tecla atual, configurável na janela. Por defeito é `` ` ``
  (`Key.Grave`), guardada nas definições do widget.
- **Aviso vermelho** quando o combate do HeroAI está ativo para esta conta.

## Arquitetura e ficheiros

```
Widgets/Automation/Helpers/AutoRota/
├── .widget                 # marcador: o gestor de widgets carrega os .py desta pasta
├── Auto Rota.py            # widget: main(), janela, tecla, ligação ao HeroAI
└── auto_rota_src/          # sem .widget, por isso não é carregado como widget
    ├── __init__.py
    ├── model.py            # dataclasses simples: EnemyCast, InterruptSlot, Decision
    ├── priorities.py       # níveis, atributos de cura, limiar de cast longo
    ├── decide.py           # lógica pura: classificar casts e escolher o interrupt
    └── game_adapter.py     # lê o jogo (Py4GWCoreLib/HeroAI) e devolve os dados de model.py
```

- **`decide.py` e `model.py` não importam o Py4GWCoreLib**, que só funciona
  dentro do jogo. Recebem dados simples e devolvem uma `Decision`, por isso
  podem ser testados num Python normal, fora do jogo.
- **`game_adapter.py`** é a única ponte para o jogo: recolhe os casts
  inimigos, os slots de interrupt, os resultados de `is_interrupt_feasible` e o
  fallback da rotação do `CombatClass`.
- **O widget** usa `CacheData()` e `CombatClass`, como o widget **EZ Cast**.
  A cada frame chama `cached_data.UpdateCombat()` e, quando passam 100 ms,
  atualiza a pré-visualização. A tecla é registada no `HOTKEY_MANAGER`.

### Fluxo de dados
```
jogo ─► game_adapter.snapshot() ─► decide.choose_interrupt(snapshot) ─► Decision
                                            │ (nenhum interrupt)
                                            ▼
                         game_adapter.rotation_fallback() ─► Decision
tecla ─► verificações ─► Decision ─► game_adapter.execute(decision) ─► UseSkill
```

## Conflito com o HeroAI e opções de skills

- **Conflito.** Se `cached_data.account_options.Combat` estiver ativo para a
  conta local, o HeroAI também está a lançar skills. A Auto Rota mostra o aviso
  e recusa todos os toques.
- **Skills ativas.** `CombatClass.IsSkillReady` depende de `is_skill_enabled`,
  que vem das opções do HeroAI em shared memory. Se a conta não tiver opções
  do HeroAI, ficam todas `False`. Depois de cada `UpdateCombat()`, a Auto Rota
  define `combat_handler.is_skill_enabled = [True] * 8` na sua própria
  instância. Isto não muda as opções guardadas do HeroAI.

## Erros

- Qualquer exceção no adapter ou no widget é apanhada, registada na consola
  (`ConsoleLog`, módulo "Auto Rota") e mostrada no histórico. O widget nunca
  deixa a exceção subir para o gestor de widgets.
- Se `GetCastingSkillID` ou os dados de uma skill falharem para um inimigo,
  esse inimigo é ignorado e os outros continuam a ser avaliados.

## Testes

- **Testes unitários** (`Widgets/Automation/Helpers/AutoRota/tests/test_decide.py`,
  com pytest e sem o jogo), que cobrem:
  - classificação nos 5 níveis;
  - prioridade entre níveis (uma ressurreição ganha a uma cura);
  - desempate pelo cast que termina mais cedo;
  - compatibilidade de `TargetAllegiance` (o Power Spike não apanha ataques);
  - pares não viáveis descartados;
  - sem candidatos, resultado `None`.
- **Validação no jogo** (manual, num PC Windows), com barra de Mesmer com
  Power Spike e Cry of Frustration:
  1. Monk inimigo a curar → Power Spike nele.
  2. Ressurreição e cura ao mesmo tempo → interrompe a ressurreição.
  3. Nenhum inimigo a fazer cast → lança a próxima skill da rotação ou "nada a fazer".
  4. Toque durante um cast → "ocupado", sem lançar nada.
  5. HeroAI com combate ligado → aviso e recusa.
  6. Em outpost → recusa.
