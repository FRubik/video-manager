# Gerenciador de Vídeos

Interface gráfica (PySide6) para gerar *contact sheets* de uma pasta de vídeos e
triar, com o teclado, o que fica e o que vai para a quarentena.

O motor de extração de frames é o mesmo do notebook `Thumbnail Maker` — inclusive
a convenção de nome das thumbnails (`meu_video.mp4.jpg`), então as thumbs que você
já gerou são reaproveitadas sem precisar gerar de novo.

## Instalar

```bash
uv tool install --editable ~/Projetos/video_manager
```

Isso coloca o comando `video-manager` em `~/.local/bin`, então ele roda de
qualquer pasta, sem `uv` na frente:

```bash
video-manager
```

Como a instalação é `--editable`, o comando aponta para o código desta pasta:
editar um arquivo já vale na próxima execução, sem reinstalar. Só é preciso
rodar `uv tool upgrade video-manager` se as **dependências** do projeto mudarem.

Para desinstalar: `uv tool uninstall video-manager`.

## Executar sem instalar

Dentro da pasta do projeto:

```bash
uv run video-manager        # comando declarado em [project.scripts]
uv run python -m video_manager
```

Atenção: esta pasta **não tem `.venv`** de propósito — o ambiente da ferramenta
instalada já contém tudo, e manter os dois duplicava ~900 MB (PySide6 é pesado,
e o uv não compartilha esses arquivos entre os dois ambientes). Qualquer
`uv run` aqui recria o `.venv` e traz a duplicação de volta.

Para rodar um script avulso contra as dependências do projeto sem recriar nada,
use o Python da própria ferramenta:

```bash
~/.local/share/uv/tools/video-manager/bin/python meu_teste.py
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

## Nota sobre abrir o vídeo no player (tecla `O`)

Duas armadilhas custaram um crash do VLC e estão resolvidas — vale saber, porque
qualquer código novo que lance um programa externo esbarra nelas de novo:

1. **Não passe URL `file://`.** O `.desktop` do VLC recebe a URL via `%U`, e
   nomes com `#`, `%`, `&` ou espaços podem ser reinterpretados no caminho. O
   caminho vai como argumento único para `xdg-open`.

2. **Não deixe o processo filho herdar o ambiente sujo.** O `import cv2`
   sobrescreve `QT_QPA_PLATFORM_PLUGIN_PATH`, `QT_QPA_FONTDIR` e
   `LD_LIBRARY_PATH` apontando para dentro do site-packages do OpenCV, que traz
   um único `libqxcb.so` ligado às libs Qt dele. Um app Qt lançado como filho
   tenta carregar aquele plugin e aborta com `Could not load the Qt platform
   plugin "xcb"` — o VLC morria com SIGABRT antes mesmo de olhar o arquivo.
   Por isso `video_manager/__init__.py` guarda `PRISTINE_ENV` (cópia do ambiente
   feita antes de qualquer import pesado) e `library.launch_env()` a entrega aos
   processos externos.

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
