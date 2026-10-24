# Combat Meter — medidor de dano e cura

Data: 2026-10-24 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`

## Objetivo

Um widget Py4GW que mostra, por membro da party, o **dano** feito a inimigos e a
**cura** feita a aliados. Para cada um mostra o total, o valor por segundo (DPS
ou HPS) e a percentagem no total da party. É independente da Auto Rota.

## Comportamento

- **Duas vistas, com botões de escolha:**
  - **Combate atual:** um combate novo começa quando chega dano ou cura depois
    de 8 s sem nada. O último combate fica visível até começar outro.
  - **Total da zona:** recomeça quando entras numa zona de combate
    (explorable) nova. Ao chegar ao outpost, o último total continua visível. O
    "por segundo" conta só o tempo em combate, ou seja a soma das durações dos
    combates.
- **Botão Reiniciar** para limpar tudo à mão.
- **Separadores Dano e Cura**, cada um com uma tabela: nome, total, por segundo
  e uma barra com a percentagem.
- **Quem conta:**
  - jogadores, heróis, mercenários e "outros" da party;
  - invocações (allegiance SpiritPet ou Minion), que contam para o dono
    (`Agent.GetOwnerID`) quando ele é da party, e senão para a linha
    "Invocacoes";
  - as outras fontes são ignoradas.
- **O que conta:**
  - dano (normal, crítico e ignora-armadura, com qualquer sinal) a inimigos;
  - cura a membros da party ou a aliados (Ally, SpiritPet, Minion).
  - O sinal dos valores não foi verificado no jogo. Por isso usa-se o valor
    absoluto, e o tipo de quem recebe (inimigo ou aliado) é que separa o dano da
    cura.
- **Linhas:** cada linha corresponde a um agente (ID), não a um nome. O nome é
  guardado quando o dano ou a cura é registado, porque os IDs dos agentes são
  reutilizados de mapa para mapa e os nomes chegam com atraso.
- **Ao ligar o widget**, os eventos acumulados enquanto estava desligado são
  descartados.
- **Pontos de vida:** o jogo envia frações da vida máxima de quem recebe.
  - Com a vida máxima conhecida (`Agent.GetMaxHealth` > 0), o valor é exato.
  - Sem ela, que é o caso habitual dos inimigos, o valor é estimado com
    80 + 20 × nível e mostrado com "~".

## Fonte dos dados

- A fila nativa `PyAgentEvents` está ligada por defeito no arranque. O widget
  esvazia-a em cada frame com `get_and_clear_events()`.
- A fachada `Py4GWCoreLib/CombatEvents.py` não é usada: está desligada ("by
  design") e chama o módulo antigo `PyCombatEvents`.
- **Restrição:** o Combat Meter é o único consumidor da fila. Se outro widget a
  esvaziar, cada um vê só parte dos eventos.
- Com o mapa inválido ou a carregar, os eventos são descartados, para não
  encherem a fila nem entrarem num combate seguinte.
- Se a captura estiver desligada, a janela mostra um aviso.

## Arquitetura

```
Widgets/Automation/Helpers/CombatMeter/
├── .widget
├── Combat Meter.py            # janela, vistas, ligação ao jogo
└── combat_meter_src/
    ├── __init__.py            # vazio
    ├── meter.py               # puro: classify_event, health_amount, CombatMeter
    └── game_source.py         # único módulo que fala com o jogo: PyAgentEvents, party, donos
Examples and tests/tests/combat_meter/test_combat_meter.py   # 11 testes offline
```

O widget fica em `Widgets/Automation/Helpers/` e não em `Widgets/Guild Wars/`,
porque o espaço no nome desta última pasta impede importar módulos a partir
dela.

## A validar no jogo

1. A janela abre e, num combate, aparecem linhas para ti e para os heróis.
2. Os números de dano fazem sentido. Se vierem todos a zero ou trocados com a
   cura, o sinal dos eventos é o contrário do assumido e a correção é em
   `classify_event`.
3. Os minions de um Necromante herói contam para o herói.
4. O "Combate atual" recomeça depois de 8 s sem combate. O "Total da zona"
   recomeça ao entrar numa zona de combate nova e continua visível no outpost.
5. Os pets de Ranger contam para o dono. Se aparecerem em "Invocacoes", o dono
   não está a ser identificado.
