# Auto Rota — assistente de combate semi-automático (Mesmer)

Data: 2026-10-24 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`

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

1. **Filtros da tecla** (ignoram o toque sem deixar registo no histórico):
   - repetição automática de uma tecla mantida premida;
   - widget em pausa, mapa a carregar ou grupo por carregar (o `main()` do
     widget não correu nos últimos 0,5 s);
   - jogador a escrever no chat (`Player.IsTyping()`) ou num campo de texto
     ImGui (`want_text_input`).
2. **Verificações.** Recusa o toque e regista o motivo no histórico se:
   - o widget HeroAI estiver ligado **e** com combate ativo para esta conta
     ("HeroAI com combate ligado");
   - o mapa não for explorable ("fora de combate (outpost)");
   - o jogador estiver morto ("personagem morto");
   - o jogador estiver derrubado, a fazer cast, ou tiverem passado menos de
     250 ms desde a última jogada ("ocupado"). Os 250 ms contam desde o envio
     da jogada, não desde o fim real do aftercast.
3. **Interrupts.** Calcula a melhor oportunidade de interrupt (secção seguinte)
   e lança-a, se existir.
4. **Rotação.** Se não houver interrupt, percorre a barra pela ordem de
   prioridade do `CombatClass` do HeroAI e lança a primeira skill que passe
   `IsSkillReady` e `IsReadyToCast` com um alvo vivo. Os interrupts com alvo
   "inimigo a fazer cast" ficam de fora (pertencem ao passo 3); interrupts com
   outro tipo de alvo, como o Overload, entram na rotação. Os alvos vêm da
   escolha automática do HeroAI (alvo chamado pelo grupo, senão o inimigo mais
   próximo dentro do alcance de procura dele), não do alvo que o jogador tem
   selecionado.
5. **Nada a fazer.** Se não houver nenhuma das duas, não faz nada e regista
   "nada a fazer".

Com uma build de Mesmer detetada, o comportamento muda conforme
`docs/superpowers/specs/2026-10-24-auto-rota-build-mode-design.md`.

A skill é lançada com `GLOBAL_CACHE.SkillBar.UseSkill(slot, alvo,
aftercast_delay=250)`, que a põe na fila de ações `ACTION`. Nunca se chama o
`HandleCombat` do HeroAI, por isso não se publicam os locks de cooldown nem de
spike de multibox. Os locks de reserva de alvo (ressurreição, remoção de hex,
cadáveres) só são publicados quando a tecla resolve o alvo para um cast real;
a pré-visualização nunca os publica.

## Escolha do interrupt

### Candidatos
- **Inimigos:** vivos, a fazer cast (`Agent.IsCasting`), a menos de
  `Range.Longbow` e com uma skill de cast diferente de 0. O tempo restante vem
  de `cast_observer.elapsed_ms` do HeroAI.
- **Interrupts do jogador:** slots com `SkillNature.Interrupt` nos dados do
  HeroAI e um tipo de alvo da tabela seguinte, que passem `IsSkillReady` e as
  verificações de adrenalina e energia (as mesmas do `IsReadyToCast`).

### Compatibilidade interrupt ↔ cast
Respeita o `TargetAllegiance` de cada interrupt nos dados do HeroAI:

| `TargetAllegiance` | Casts que pode interromper |
|---|---|
| `EnemyCasting` | qualquer cast |
| `EnemyCastingSpell` | só spells |
| `EnemyCastingSpellOrChant` | spells e chants |
| `EnemyAttacking` | só skills de ataque |

"Spell" quer dizer um `SkillType` entre Spell, Hex, Enchantment, Well, Ward,
WeaponSpell e ItemSpell. Glyphs e rituais não são spells. Signets, shouts,
stances e outros tipos só podem ser apanhados por `EnemyCasting`.

Cada par só é válido se `HeroAI.interrupt.is_interrupt_feasible(alvo, skill,
fast_casting, ping)` devolver `True`. Essa função trata do alcance, do ping, do
Fast Casting e dos hexes que abrandam. A latência da fila de ações (cerca de
50–100 ms) não entra nesse cálculo, tal como acontece no HeroAI.

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

**Ordem e desempate:** os casts são ordenados por (nível, tempo restante) e,
num empate exato, fica o primeiro na ordem de entrada. Para cada cast, os
interrupts são testados pela ordem de prioridade do `CombatClass` (entre
interrupts, é a ordem da barra). Ganha o primeiro par viável. Se o cast mais
prioritário não tiver nenhum interrupt viável, passa ao seguinte.
`is_interrupt_feasible` só é chamado para interrupts que conseguem apanhar
aquele tipo de cast.

A tabela de níveis e os nomes dos atributos de cura ficam em `priorities.py`.

## Janela de pré-visualização

Uma janela ImGui pequena (`AlwaysAutoResize`) com:
- **Próxima jogada:** recalculada a cada 100 ms. Formatos:
  `Power Spike -> Monk (Orison of Healing) [Interrupt: Cura]` e
  `<skill> -> <alvo> [Rotacao]`. Para skills que reservam alvos entre contas,
  a pré-visualização procura o alvo sem o reservar (ressurreição e remoção de
  hex; se não houver alvo, a skill não aparece). Para skills de cadáveres
  mostra `(alvo ao carregar)`, porque a procura do HeroAI escreve na consola a
  cada chamada.
  Com uma verificação a falhar (exceto "ocupado") mostra
  `em pausa (<motivo>)`.
- **Histórico:** as últimas 5 entradas no formato `HH:MM:SS  <texto>`
  (jogadas, `recusado: <motivo>`, `nada a fazer`, `erro: ...`).
- **Tecla:** acento grave (`Key.VK_OEM_3`) por defeito, ou F1 a F5. Fica
  guardada em `Widgets/Config/auto_rota.ini`, secção `AutoRota`, chave
  `hotkey`, com âmbito **global** (todas as contas da máquina partilham-na).
- **Aviso vermelho** quando o widget HeroAI está ligado com combate ativo.

## Arquitetura e ficheiros

```
Widgets/Automation/Helpers/AutoRota/
├── .widget                 # marcador: o gestor de widgets carrega os .py desta pasta
├── Auto Rota.py            # widget: main(), janela, tecla, histórico
└── auto_rota_src/          # sem .widget, por isso não é carregado como widget
    ├── __init__.py         # vazio
    ├── model.py            # dataclasses simples: EnemyCast, InterruptSlot, Decision
    ├── priorities.py       # níveis, rótulos, atributos de cura, limiar de cast longo
    ├── decide.py           # lógica pura: classify, can_hit, choose_interrupt
    └── game_adapter.py     # única ponte para o jogo (Py4GWCoreLib/HeroAI)
Examples and tests/tests/auto_rota/test_auto_rota_decide.py   # testes offline
```

- **`model.py`, `priorities.py` e `decide.py` não importam o Py4GWCoreLib.**
  Recebem dados simples e devolvem uma `Decision`, por isso são testados num
  Python normal, fora do jogo.
- **`game_adapter.py`** tem um `CombatClass` **privado**. O `CacheData` é um
  singleton partilhado com o HeroAI e outros widgets, e só é lido. Em cada
  `next_decision()`, `_sync_combat()` faz `Update(cached_data)` e
  `PrioritizeSkills()` na instância privada e força todas as skills e a escolha
  automática de alvos. Nada disto toca no estado do HeroAI.
- **O widget** chama `CacheData.Update()` em cada frame (o próprio `Update`
  limita-se a 75 ms) e a pré-visualização a cada 100 ms. A tecla é registada no
  `HOTKEY_MANAGER`. O `HOTKEY_MANAGER.update()` e a fila `ACTION` são
  processados pelo widget de sistema **Environment Upkeeper**, que tem de estar
  ligado.

### Fluxo de dados
```
pré-visualização: next_decision(preview=True) ─► describe() ─► janela
tecla ─► filtros ─► blocker() ─► next_decision() ─► execute() ─► UseSkill
                                      │                        └─► describe() ─► histórico
                                      ▼
   _sync_combat() ─► choose_interrupt(_enemy_casts(), _interrupt_slots(), _is_feasible)
                                      │ (nenhum interrupt)
                                      ▼
                             _rotation_decision()
```

## Conflito com o HeroAI

Se o widget HeroAI estiver ligado e `account_options.Combat` estiver ativo
para a conta local, o HeroAI também está a lançar skills. A Auto Rota mostra o
aviso e recusa todos os toques. Outros widgets que lançam skills sozinhos (por
exemplo o EZ Cast) não são detetados e devem ser desligados.

## Erros

- Erros da tecla: consola (`ConsoleLog`, remetente "Auto Rota", com traceback)
  e histórico (`erro: ...`).
- Erros da pré-visualização: a linha mostra `erro (ver consola)`; cada mensagem
  distinta é registada uma vez.
- Erros no `main()`: registados uma vez por mensagem distinta.
- Falhas a ler um inimigo: esse inimigo é ignorado e os outros continuam a ser
  avaliados. Cada par (inimigo, skill) é registado uma vez como Warning.
- Nenhuma exceção sobe para o gestor de widgets, e o `PyImGui.end()` é sempre
  chamado.

## Testes

- **Testes offline:** `Examples and tests/tests/auto_rota/test_auto_rota_decide.py`
  (`unittest` da biblioteca padrão, 20 testes). Correm com
  `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`.
  Cobrem:
  - os níveis de prioridade e o rótulo de cada nível;
  - a tabela completa de compatibilidade interrupt ↔ cast;
  - a regra de que o nível conta antes do tempo restante;
  - o desempate;
  - a passagem para o cast seguinte quando um não é viável;
  - as chamadas a `feasible` só quando necessárias;
  - entradas vazias.
- **Verificação estática:** Pyright 1.1.390 com Python 3.13, 0 erros.
- **Validação no jogo** (manual, num PC Windows), com barra de Mesmer com
  Power Spike e Cry of Frustration:
  1. Monk inimigo a curar → Power Spike nele.
  2. Ressurreição e cura ao mesmo tempo → interrompe a ressurreição.
  3. Nenhum inimigo a fazer cast → lança a próxima skill da rotação ou mostra "nada a fazer".
  4. Toque durante um cast → "ocupado", sem lançar nada.
  5. HeroAI com combate ligado → aviso e recusa.
  6. Em outpost → recusa.
  7. Mudar a tecla para F2 → o acento grave deixa de funcionar, o F2 funciona, e a escolha mantém-se após reiniciar.
  8. Manter a tecla premida → uma só jogada.
  9. Escrever o acento grave no chat → nenhuma jogada.
  10. Resurrection Signet na barra com um aliado morto → a pré-visualização mostra
      esse aliado e a tecla ressuscita-o. Sem ninguém morto, o Resurrection Signet
      não aparece como próxima jogada.
