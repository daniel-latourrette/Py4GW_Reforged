# Auto Rota — vigia de casts inimigos com interrupt de um toque

Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
Depende de: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`,
`docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md` e
`docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md`

## Objetivo

Hoje, a única forma de agir sobre os casts inimigos é ligar o ciclo automático.
A vigia mostra ao jogador, numa janela própria e em tempo real, que inimigos ao
alcance estão a fazer cast. Para cada um mostra a skill, uma barra de progresso
estimada, a cor do escalão de prioridade e se há um interrupt pronto que chegue
a tempo. Com o ciclo desligado, uma tecla dispara **um** interrupt: o mesmo que
a Auto Rota escolheria nesse instante. O jogador decide quando interromper.

## Fora do âmbito

- **Uma grelha por skill**, com sim ou não para cada interrupt da barra em cada
  cast. Exigiria uma função nova no código partilhado do HeroAI e custaria mais
  por frame. A lista mostra só o interrupt que a Auto Rota usaria.
- **O alvo do cast** (quem está a ser ressuscitado, por exemplo).
  `Agent.GetCastingTarget` devolve sempre 0.
- **Piscar a janela do Guild Wars** quando começa uma ressurreição.
  `PySystem.window.flash_window` nunca foi testado no jogo.
- **Disparar o interrupt com um clique numa linha.** O clique só seleciona o
  inimigo como alvo; quem dispara é a tecla.
- **Mudanças no HeroAI, no BuildMgr ou no ciclo automático**, que continua a
  escolher exatamente o mesmo de hoje.

## Janela

- **Janela própria:** `Auto Rota: casts##auto_rota_casts`, aberta com
  `PyImGui.begin_with_close` e as flags `AlwaysAutoResize | NoCollapse`.
  - Desenhada em `main()` logo a seguir à janela principal, dentro de um
    `try/finally` com `PyImGui.end()`.
  - Abre e fecha com uma caixa "Vigia de casts" na janela da Auto Rota, ou com
    o X da própria janela.
  - O estado aberto ou fechado fica em `Widgets/Config/auto_rota.ini`, na secção
    `AutoRota`, chave `cast_watch_open` (booleana, ligada por defeito).
- **Linha de topo:**
  - `Interrupt (<tecla>): <skill> -> <inimigo> (<skill inimiga>)` na cor de
    "ligado" (`_ON_COLOR`), quando há um interrupt viável.
    - A linha é cortada com `...` à largura da lista (`fit_text`). Sem isso, a
      janela, que se ajusta ao conteúdo, mudaria de largura a cada alvo novo.
    - Se a tecla de interrupt for igual à do ciclo ou à dos buffs, o que a deixa
      sem efeito, mostra `(tecla ignorada)` em vez do nome da tecla.
  - Senão, `sem interrupt viavel`, a cinzento.
  - Com o ciclo ligado, acrescenta a cinzento
    `tecla em pausa: o ciclo esta ligado`.
  - Com a Auto Rota parada por um motivo de paragem (outpost, morte, combate do
    HeroAI), mostra `em pausa (<motivo>)` e a lista fica vazia.
- **Lista:** uma região `begin_child` com tamanho fixo, para a janela não saltar
  quando as linhas mudam 10 vezes por segundo.
  - Tem no máximo 6 linhas (`WATCH_MAX_ROWS`). Se houver mais casts, uma última
    linha diz `+N casts`.
  - Sem casts, mostra `nenhum inimigo a fazer cast` a cinzento.
  - É uma tabela com `begin_table` e as flags `RowBg | BordersInnerV |
    SizingFixedFit | NoSavedSettings`, sempre dentro de `try/finally`.
- **Colunas de cada linha:**

| Coluna | Conteúdo |
|---|---|
| Inimigo | `selectable` com `SpanAllColumns`, marcado quando o inimigo é o alvo atual. Um clique chama `Player.ChangeTarget(agent_id)`, se o agente ainda for válido. A linha que a tecla dispararia começa por `> `. |
| Ícone | `ImGui.DrawTexture(path, 20, 20)` com o caminho de `GLOBAL_CACHE.Skill.ExtraData.GetTexturePath`; `?` quando o caminho vem vazio. |
| Skill | Nome da skill inimiga, na cor do escalão. |
| Cast | `progress_bar` com largura fixa de 90 (com -1, `AlwaysAutoResize` reduz a barra a nada), tingida com a cor do escalão. O texto da barra vem de `cast_progress` (ver abaixo). |
| Interrupt | `a tempo: <a tua skill>` na cor de "ligado", ou `sem interrupt a tempo` a cinzento. |

- **Ordem:** a mesma da escolha da Auto Rota, primeiro por escalão e depois
  pelo cast que acaba mais cedo.
- **Cores dos escalões:** ficam em `priorities.py`, num `TIER_COLORS` em RGBA,
  junto a `TIER_LABELS`:

| Escalão | Cor |
|---|---|
| Ressurreição | (0.95, 0.40, 0.40, 1.0) |
| Cura | (1.00, 0.65, 0.25, 1.0) |
| Elite | (1.00, 0.84, 0.30, 1.0) |
| Cast longo | (0.55, 0.75, 1.00, 1.0) |
| Outro | (0.55, 0.55, 0.55, 1.0) |

## Barra de progresso (estimativa)

- **Origem dos dados:** não vêm do jogo. O tempo decorrido vem do
  `cast_observer` do HeroAI, que regista o primeiro frame em que viu o cast. A
  duração é o tempo base da skill. A barra não conta com Fast Casting nem com
  hexes que abrandam o cast do inimigo.
- **Função pura:** `cast_progress(cast, seconds_since_read) -> CastProgress`,
  onde `CastProgress` tem `fraction: Optional[float]` e `label: str`.
  - Quando o cast ainda não foi visto (`elapsed_ms=None`), devolve
    `fraction=None` e `label="?"`. A barra fica vazia.
  - Quando `activation_ms <= 0`, devolve o mesmo.
  - Nos outros casos calcula
    `decorrido = elapsed_ms + seconds_since_read * 1000`.
  - Se `decorrido > activation_ms + 300`, devolve `fraction=1.0` e
    `label="a terminar?"`. Isto apanha casts abrandados ou a mesma skill lançada
    outra vez sem pausa.
  - Senão, devolve `fraction = clamp(decorrido / activation_ms, 0, 1)` e
    `label = f"{max(0, activation_ms - decorrido) / 1000:.1f}s"`.
- **Ritmo de atualização:** o widget lê o jogo de 100 em 100 ms e calcula a
  barra em cada frame com `seconds_since_read`, por isso a barra anda suave sem
  ler o jogo mais vezes.

## Tecla de um toque

- **Configuração:**
  - Terceira tecla, "Tecla interrupt", F3 por defeito, escolhida na mesma lista
    `_KEY_CHOICES`.
  - Guardada em `auto_rota.ini`, chave `interrupt_hotkey`.
  - Tem o seu próprio `KeyEdge`.
- **Precedência quando há teclas iguais:** o ciclo ganha aos buffs, e os buffs
  ganham ao interrupt. A janela mostra um aviso por cada tecla ignorada.
  - A regra fica numa função pura em `key_edge.py`,
    `shadowed_positions(indices: Sequence[int]) -> frozenset[int]`.
  - A função devolve as posições cuja tecla já foi escolhida numa posição
    anterior.
- **Ao carregar:**
  1. Se `_press_allowed()` recusar (o jogo sem foco, ou a escrever), a função
     pára aí; o próprio `_press_allowed()` regista o motivo.
  2. Com o ciclo ligado, regista em "Ultimo toque ignorado"
     `ciclo ligado: a tecla de interrupt so funciona com ele desligado`.
  3. Com `blocker()` a dar um motivo, ou com a passagem da build ocupada, regista
     `interrupt: <motivo>`. Não há fila nem nova tentativa: o jogador carrega
     outra vez.
  4. Lê o jogo de novo com `cast_watch(_guard_ids)`, porque a viabilidade
     depende do instante, e guarda essa leitura como a da lista.
  5. A decisão é `interrupt_from_rows(linhas, Tier.OTHER)`. Considera **todos os
     escalões**, também no modo build: o limite do modo build só existe para dar
     lugar à lógica da build, que com o ciclo desligado não corre.
  6. Se não houver decisão, regista `sem casts inimigos ao alcance` (lista vazia)
     ou `nenhum interrupt pronto chega a tempo`. Não lança nada.
  7. Se houver, chama `execute(decisão)`, que partilha o debounce com o ciclo, e
     regista no histórico `1 toque: <describe(decisão)>`.
- **Guarda de hexes:** é sempre respeitada, porque os `_guard_ids` entram na
  leitura.

## Regra partilhada (núcleo puro)

### `model.py`

- O `EnemyCast` ganha o campo `elapsed_ms: Optional[int] = 0`. Guarda o tempo
  decorrido medido pelo `cast_observer`, ou `None` quando o cast ainda não foi
  visto. O valor por defeito mantém válidos os testes e as chamadas que já
  existem.
  - Na implementação substituiu o `elapsed_known: bool` previsto. O
    `remaining_ms` vem cortado em zero, e só com o tempo real é possível mostrar
    `a terminar?`.
- Tipo novo:
  `CastRow(cast: EnemyCast, tier: Tier, slot: Optional[InterruptSlot])`,
  imutável. `slot` é o primeiro interrupt, pela ordem de prioridade do
  `CombatClass`, que acerta no cast e chega a tempo. `None` quer dizer que
  nenhum chega a tempo.

### `decide.py`

- `cast_rows(casts, slots, feasible) -> list[CastRow]` devolve todos os casts,
  ordenados com `_cast_key`, cada um com o seu primeiro slot viável.
- `interrupt_from_rows(rows, max_tier=Tier.OTHER) -> Optional[Decision]` percorre
  as linhas e pára ao passar `max_tier`. Devolve a decisão da primeira linha com
  slot.
- `choose_interrupt` passa a usar os mesmos ajudantes privados:
  - `_first_slot(cast, slots, feasible)`;
  - `_interrupt_decision(cast, slot, tier)`, que cria a `Decision` com o mesmo
    `label` de hoje.

  O `choose_interrupt` continua preguiçoso e com o mesmo contrato: só chama
  `feasible` até encontrar a primeira escolha.
- **Garantia:** para todos os casos de teste e todos os escalões,
  `interrupt_from_rows(cast_rows(c, s, f), t) == choose_interrupt(c, s, f, t)`.

### `cast_watch.py` (novo, puro)

- `CastProgress` e `cast_progress`, descritos acima.
- `WATCH_MAX_ROWS = 6`.
- `interrupt_text(row, skill_name) -> str` devolve `a tempo: <nome>` ou
  `sem interrupt a tempo`.

## Ligação ao jogo

### `game_adapter.py`

- **Alcance da procura:** `_enemy_casts` passa a procurar casts até à distância
  de spell (`Range.Spellcast`, 1248), em vez de até à de arco longo (1498). O
  ciclo não muda de comportamento: `is_interrupt_feasible`
  (`Py4GWCoreLib/HeroAI/interrupt.py`) já recusa qualquer alvo para lá desse
  alcance, ou de 144 nos interrupts corpo a corpo. Assim, a lista mostra
  exatamente os casts que a Auto Rota considera.
- **Elapsed:** `_describe_cast` preenche `elapsed_ms` com o resultado de
  `cast_observer.elapsed_ms(...)`, incluindo `None`.
- **Métodos públicos novos:**
  - `cast_watch(blocked_skill_ids: Iterable[int] = ()) -> list[CastRow]` faz um
    só `_sync_combat(blocked_skill_ids)` e devolve
    `cast_rows(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)`.
  - `agent_name(agent_id) -> str` devolve `Agent.GetNameByID`, ou
    `agente <id>` enquanto o nome não estiver pronto.
  - `skill_name(skill_id) -> str` é a versão pública de `_skill_name`.
  - `skill_icon_path(skill_id) -> str` devolve
    `GLOBAL_CACHE.Skill.ExtraData.GetTexturePath`.
- **`next_decision`:** ganha o argumento opcional `rows`. Quando vem, a escolha
  do interrupt usa `interrupt_from_rows(rows)` em vez de ler os casts outra vez.
  A rotação a seguir não muda.

### `Auto Rota.py`

- **Leitura única por tick:** `_update_preview` faz uma só leitura de 100 em
  100 ms: `rows = _adapter.cast_watch(_guard_ids)`.
  - Guarda `_watch_rows`, o instante da leitura (`_watch_read_s`) e, por linha,
    o nome do inimigo, o nome da skill e o ícone. Assim os nomes não são
    procurados em cada frame.
  - No modo genérico, a pré-visualização usa
    `next_decision(preview=True, ..., rows=rows)`.
  - No modo build, usa `interrupt_from_rows(rows, BUILD_MODE_MAX_TIER)`.
  - Quando há um motivo de paragem, a lista é limpa.
- **Desenho:** `_draw_cast_watch()` é chamado em `main()` depois de
  `_draw_window()`, só quando `cast_watch_open` está ligado. Devolve o agente
  clicado, se houver, e a ação `ChangeTarget` acontece fora da tabela.
- **Teclas:** a tecla de interrupt é lida em `main()` depois das teclas do ciclo
  e dos buffs, dentro do seu próprio `try/except`. O combo "Tecla interrupt" fica
  junto aos outros dois.
- **Tooltip:** uma linha nova, "Tecla interrupt (F3): com o ciclo desligado,
  interrompe uma vez o cast mais importante".

## Erros

- Um erro ao ler a lista é registado uma vez na consola. A janela mostra
  `erro (ver consola)` e a Auto Rota continua.
- Um erro ao desenhar fica contido no `try/finally` de cada
  `begin`/`begin_child`/`begin_table`, para nunca desequilibrar a pilha do
  ImGui.
- Um erro na tecla de interrupt vai para o histórico (`erro: ...`) e para a
  consola, como nas outras teclas.

## Testes offline

### `test_auto_rota_decide.py`

- **Equivalência:** para cada caso de escolha de interrupt que já existe e para
  cada `Tier`, `interrupt_from_rows(cast_rows(...), t)` é igual a
  `choose_interrupt(..., t)`.
- **Linhas:**
  - `cast_rows` mantém a ordem da escolha;
  - inclui casts sem slot, com `slot=None`;
  - dá a cada cast o primeiro slot viável pela ordem de prioridade.
- **Teclas:** `shadowed_positions` sem repetidos, com o ciclo e os buffs iguais,
  com as três teclas iguais e com os buffs e o interrupt iguais.

### `test_auto_rota_cast_watch.py` (novo)

- **`cast_progress`:**
  - `?` quando o cast não foi visto;
  - `?` com `activation_ms` a 0;
  - meio do cast;
  - avanço com `seconds_since_read`;
  - limite de 1.0;
  - `a terminar?` depois de `activation + 300`;
  - texto com uma casa decimal.
- **`interrupt_text`:** com slot e sem slot.

Os testes já existentes da Auto Rota, da guarda e do Combat Meter continuam a
passar. O código alterado passa no Pyright (`--pythonplatform Windows`), no
Black a 120 e no isort.

## Validação no jogo

1. **Janela:** a janela "Auto Rota: casts" abre e fecha pela caixa e pelo X, e
   lembra-se do estado depois de reiniciar o widget.
2. **Lista:** com inimigos a fazer cast, as linhas aparecem pela ordem certa e
   com as cores certas. A barra faz sentido: anda durante o cast e mostra `?`
   enquanto o cast ainda não foi visto.
3. **Tecla:** com o ciclo desligado, a F3 interrompe o cast da linha marcada com
   `>` e regista `1 toque: ...`. Com o ciclo ligado, é ignorada e o motivo
   aparece.
4. **Clique:** um clique numa linha seleciona esse inimigo.
5. **Estabilidade:** a janela não salta enquanto as linhas mudam.
6. **Custo:** sem quebras de frames com vários inimigos a fazer cast.

## Limites e riscos

- **A barra é uma estimativa:** usa o tempo base e o primeiro frame em que o
  cast foi visto. Ver "Barra de progresso".
- **Casts muito curtos:** casts de 0,5 s ou menos quase nunca dão para cortar e
  podem piscar na lista. Aparecem como as outras linhas, com
  `sem interrupt a tempo`.
- **Clique seguido de tecla:** a mudança de alvo passa pela fila de ações. Uma
  F3 carregada até cerca de 0,1 s depois do clique é recusada como "ocupado".
- **O jogo também recebe a tecla:** as teclas são lidas sem as bloquear, por
  isso o jogo recebe a F3.
- **Viabilidade calculada para todos os casts:** a lista testa a viabilidade de
  cada cast a cada 100 ms, e o ciclo só testa até à primeira escolha. O custo é
  pequeno com poucos inimigos, mas não foi medido. Se pesar, a leitura completa
  pode passar a correr só com a janela aberta.
- **Diferenças com a "Próxima jogada" no modo build:** com o ciclo desligado, a
  linha "Próxima jogada" segue o limite do modo build (até elite), e a tecla
  considera todos os escalões. A janela mostra a escolha da tecla.
