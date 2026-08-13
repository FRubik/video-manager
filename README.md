# Gerenciador de Vídeos

Interface gráfica (PySide6) para gerar *contact sheets* de uma pasta de vídeos e
triar, com o teclado, o que fica e o que vai para a quarentena.

O motor de extração de frames é o mesmo do notebook `Thumbnail Maker` — inclusive
a convenção de nome das thumbnails (`meu_video.mp4.jpg`), então as thumbs que você
já gerou são reaproveitadas sem precisar gerar de novo.

## Executar

```bash
uv run --project ~/Projetos/video_manager video-manager
```

Atalho útil no `~/.zshrc`:

```bash
alias videos='uv run --project ~/Projetos/video_manager video-manager'
```

## Como funciona

### 1. Tela inicial

- **Pastas**: vídeos, thumbnails e a pasta de descartes (preenchida sozinha como
  `<pasta de vídeos>/_para_apagar`, mas pode apontar para qualquer lugar).
- **Gerar thumbnails**: desmarcado, o programa vai direto para a revisão usando as
  thumbs existentes. Marcado, gera antes — com a opção *somente vídeos que ainda
  não têm thumbnail*, que é o caso comum quando você adiciona vídeos novos.
- **Sessão de revisão**:
  - *Revisar todos* — passa por tudo que tem thumbnail;
  - *Verificação randômica* — sorteia N vídeos e a sessão termina neles, para
    fatiar uma pasta grande ao longo de vários dias;
  - *Pular vídeos que já revisei* — usa o histórico para não repetir o que você
    já decidiu em sessões anteriores.

O painel de resumo mostra quantos vídeos existem, quantos têm thumbnail, quantos
já foram revisados e quantos entram nesta sessão.

### 2. Tela de revisão

Uma thumbnail por vez, ocupando a janela, com a lista da sessão à direita.

| Tecla | Ação |
|---|---|
| `D` ou `Del` | marca para apagar e avança |
| `K` | marca para manter e avança |
| `←` / `→` | navega (dá para voltar e trocar a decisão) |
| `Espaço` | avança sem decidir |
| `O` | abre o vídeo no player padrão do sistema |
| `Z` ou clique | alterna entre ajustar à janela e zoom 1:1 |
| `Enter` | aplica as decisões e encerra a sessão |

Nada é movido enquanto você decide — as marcações só são aplicadas em **Aplicar e
finalizar** (ou no fim da sessão, que pergunta), sempre com confirmação.

### 3. O que acontece ao aplicar

- Vídeos marcados como *apagar* são **movidos** para a pasta de descartes (nunca
  apagados); nomes repetidos ganham sufixo `(2)`, `(3)`… em vez de sobrescrever.
- A **thumbnail continua** na pasta de thumbs, para você reavaliar o descarte
  pela imagem antes de apagar de vez.
- Cada movimento é registrado em `_movimentos.jsonl` dentro da pasta de descartes
  (origem, destino e data), o que permite desfazer manualmente se precisar.

## Arquivos de estado

| Arquivo | Onde | Para quê |
|---|---|---|
| `.video_manager_state.json` | pasta de thumbnails | histórico de decisões (alimenta o "pular já revisados") |
| `_movimentos.jsonl` | pasta de descartes | log dos vídeos movidos |
| `config.json` | `~/.config/video_manager/` | últimas pastas e opções usadas |

O histórico fica junto das thumbs de propósito: se a pasta mudar de lugar ou de
máquina, ele vai junto.

## Estrutura

```
video_manager/
├── config.py      preferências persistidas
├── library.py     varredura, pareamento vídeo↔thumb, sessão, quarentena
├── thumbs.py      extração dos frames e montagem da grade (motor do notebook)
├── worker.py      geração em thread separada
├── ui_setup.py    tela inicial
├── ui_review.py   tela de revisão
└── app.py         janela principal
```
