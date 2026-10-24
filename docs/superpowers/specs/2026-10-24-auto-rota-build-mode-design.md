# Auto Rota — modo build

Data: 2026-10-24 · Estado: design aprovado · Branch: `feature/auto-rota`
Depende de: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`

## Objetivo

Quando a barra do jogador corresponde a uma build de Mesmer do repositório
(`Py4GWCoreLib/Builds/Mesmer/`), cada toque na tecla da Auto Rota passa a usar
a lógica otimizada dessa build em vez da rotação genérica do HeroAI. A camada
de interrupts da Auto Rota continua à frente, mas só para os casts mais
importantes. Build de referência para desenho e testes: **Energy Surge**.

Continua a valer a regra base: **um toque = no máximo uma skill**, e o widget
nunca age sozinho.

## Fora do âmbito

- Pré-visualizar a jogada exata da build: não existe API de simulação, e uma
  simulação publicaria reservas de alvo para as outras contas.
- Builds de outras profissões e builds de farm.
- Interruptor na janela para desligar o modo build: entra automaticamente
  quando há correspondência.
- Copiar ou alterar a lógica das builds.

## Deteção da build

- A Auto Rota tem o seu próprio `BuildRegistry()` (`Py4GWCoreLib/BuildMgr.py:2112`).
- No `main()` do widget, calcula a assinatura da barra (profissão primária,
  secundária e as 8 skills). Só quando a assinatura muda é que resolve a build
  com `registry.GetBestBuild(primary, secondary, skills)` e cria a instância
  que vai usar.
- A build resolvida só é aceite se cumprir as três condições (regra pura,
  testada offline):
  1. `required_primary == Profession.Mesmer`;
  2. não é candidata a fallback (`is_fallback_candidate` falso). Isto exclui
     o HeroAI genérico, que o `GetBestBuild` devolve quando nada corresponde;
  3. não substitui o `ProcessSkillCasting` do `BuildMgr`. Isto exclui a build
     de farm `SF_Mes_vaettir`, que lança várias skills seguidas com esperas de
     1000 ms.
- Builds aceites hoje: Energy Surge, Ineptitude, Keystone Signet, Panic,
  Psychic Instability + Wastrel's e Holy Inept (Me/Mo).
- Na instância aceite, a Auto Rota faz `SetFallback(None, None)`. Assim o
  `ResolveFallback()` devolve `None` e a passagem nunca chama o HeroAI genérico,
  que atacaria com a arma, mudaria de alvo e mexeria no `combat_handler`
  partilhado.
- Não se chama `set_cached_data` na build. Assim a build lê da shared memory as
  opções de skills ativas do HeroAI, que valem todas "ativas" quando não
  existem. Se o jogador tiver skills desligadas no painel do HeroAI, a build
  respeita isso.
- A primeira resolução importa todos os módulos de builds (cerca de 120
  ficheiros, uma vez por sessão). As resoluções seguintes usam a cache.

## Comportamento ao carregar na tecla

Os filtros da tecla e as verificações (`blocker()`) mantêm-se como na spec base.
Junta-se uma nova razão de "ocupado": está uma passagem da build a decorrer.

**Sem build detetada:** tudo igual à spec base.

**Com build detetada:**
1. **Interrupts importantes (no callback da tecla, de imediato).**
   `choose_interrupt` só considera casts dos níveis Ressurreição, Cura e Elite
   (constante `BUILD_MODE_MAX_TIER = Tier.ELITE` em `priorities.py`). Se houver
   um par viável, lança-o como hoje e a jogada acaba aí.
2. **Pedido de passagem da build.** Senão, o callback só marca "passagem
   pedida". Não corre a build ali, porque as esperas da build contam tempo real
   e travariam o frame do widget que trata as teclas.
3. **Passagem da build (no `main()` do widget, ao longo de vários frames).**
   - No frame seguinte, o widget cria o gerador `build.ProcessSkillCasting()`
     e limpa o registo da última skill lançada.
   - Avança o gerador com um `next()` por frame.
   - A passagem acaba quando o gerador termina ou ao fim de 500 ms. No
     segundo caso, chama-se `close()`.
   - A build pode usar os seus próprios interrupts (por exemplo o Cry of
     Frustration no inimigo mais rodeado). Não há veto.
4. **Resultado da passagem.**
   - Se a build lançou uma skill, regista-a no histórico:
     `Energy Surge -> <alvo> [Build: Energy Surge]`. O alvo aparece como
     "(sem alvo)" quando o id do alvo é 0.
   - Se não lançou nada, corre no mesmo frame a rotação privada da Auto Rota,
     com as skills da build mascaradas
     (`CombatClass.ApplyBlockedSkillIDs(build.GetBlockedSkills())`). Assim só se
     usam skills fora da build.
   - Se nem isso lançar nada, regista "nada a fazer".
5. Sem build detetada, a máscara da rotação privada é limpa
   (`ApplyBlockedSkillIDs([])`).

## Registo da última skill lançada (alteração no `BuildMgr`)

Alteração aditiva em `Py4GWCoreLib/BuildMgr.py`, o dono do lançamento:
- no `__init__`: `self.last_cast: tuple[int, int] | None = None`;
- em `CastSkillID`, logo a seguir ao `GLOBAL_CACHE.SkillBar.UseSkill(...)`:
  `self.last_cast = (skill_id, target_agent_id)`.

Nada mais muda para quem já usa o `BuildMgr`. Todos os lançamentos das builds
de Mesmer e dos helpers `Builds/Skills/*` passam por `CastSkillID`. Esta é a
única alteração fora da pasta da Auto Rota.

## Janela

- Nova linha: `Build: Energy Surge`, ou `Build: nenhuma (rotacao generica)`.
- **Próxima jogada, com build:** mostra o interrupt importante, se houver um
  viável. Senão mostra `jogada da build (decidida ao carregar)`.
- **Histórico:** entradas da build com o rótulo `[Build: <nome>]`. As da
  rotação e dos interrupts ficam como hoje.

## Componentes

| Ficheiro | Mudança |
|---|---|
| `auto_rota_src/priorities.py` | `BUILD_MODE_MAX_TIER = Tier.ELITE` |
| `auto_rota_src/decide.py` | `choose_interrupt(..., max_tier: Tier = Tier.OTHER)` ignora casts acima do limite; nova função pura `is_eligible_build(candidate) -> bool` |
| `auto_rota_src/model.py` | `BuildCandidate(primary_is_mesmer: bool, is_fallback_candidate: bool, overrides_skill_casting: bool)` |
| `auto_rota_src/build_mode.py` (novo) | Ponte para o `BuildRegistry`: assinatura da barra, resolução e cache da build, `SetFallback(None, None)`, criação, avanço e timeout da passagem, leitura do `last_cast` |
| `auto_rota_src/game_adapter.py` | `next_decision(preview, max_tier)` passa o limite de nível ao `choose_interrupt`; `rotation_after_build(blocked_skill_ids)` aplica a máscara e devolve a jogada da rotação; o `blocker()` passa a devolver "ocupado" durante uma passagem |
| `Auto Rota.py` | Callback marca a passagem pedida; `main()` avança a passagem; linha "Build"; textos da pré-visualização e do histórico |
| `Py4GWCoreLib/BuildMgr.py` | Campo `last_cast` (secção anterior) |

Tal como na spec base, só `game_adapter.py` e `build_mode.py` falam com o jogo.
`decide.py`, `model.py` e `priorities.py` continuam puros.

## Efeitos secundários aceites

Só acontecem numa passagem real da build, ou seja depois de um toque na tecla,
nunca na pré-visualização:
- a build publica intenções e reservas de alvo na shared memory, como faz no
  HeroAI (por exemplo, a reserva de alvo do Shatter Hex);
- `CastSkillIDAndRestoreTarget` pode voltar a selecionar o alvo anterior;
- os resultados dos interrupts da build entram no registo de sucesso/falha do
  HeroAI.

## Erros

- Exceção ao resolver a build: fica "Build: nenhuma" e o erro é registado uma
  vez. A Auto Rota continua no modo genérico.
- Exceção a meio da passagem: o gerador é fechado, o histórico mostra
  `erro: ...` e o erro vai para a consola.
- O timeout de 500 ms fecha a passagem sem erro. Se nada foi lançado, segue-se
  a rotação.

## Testes

- **Offline** (no ficheiro de testes existente):
  - `choose_interrupt` com `max_tier=Tier.ELITE` ignora casts de cast longo e
    de "outro", e continua a escolher ressurreição, cura e elite;
  - com o valor por defeito, tudo igual (os 20 testes atuais não mudam);
  - `is_eligible_build` aceita uma build de Mesmer normal, rejeita uma
    candidata a fallback, uma build de outra profissão e uma build que
    substitui o `ProcessSkillCasting`.
- **Pyright:** 0 erros na pasta da Auto Rota, nos testes e em `BuildMgr.py`
  (sem erros novos).
- **No jogo**, com a barra Energy Surge (Air of Superiority, Energy Surge, EVAS
  e Cry of Frustration, mais Power Drain):
  1. A janela mostra `Build: Energy Surge`.
  2. Um Monk inimigo a curar é interrompido pela Auto Rota
     (`[Interrupt: Cura]`).
  3. Um inimigo a fazer cast de algo pouco importante: a Auto Rota não
     interrompe, e a build pode usar o Cry of Frustration (`[Build: Energy Surge]`).
  4. Sem casts inimigos, perto de inimigos: sai Energy Surge ou Air of
     Superiority pela build.
  5. Uma skill fora da build (por exemplo uma skill de PvE extra) só sai pela
     rotação, quando a build não tem nada para fazer.
  6. Carregar várias vezes muito depressa: no máximo uma skill por toque, e
     "ocupado" durante a passagem.
  7. Trocar uma skill obrigatória da build: a janela passa a
     `Build: nenhuma (rotacao generica)` e o comportamento volta ao genérico.
