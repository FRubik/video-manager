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

- **Pastas**: vídeos, thumbnails, descartes (`<pasta de vídeos>/_para_apagar`) e
  *talvez* (`<pasta de vídeos>/_talvez`). As duas últimas são preenchidas
  sozinhas e acompanham a troca da pasta de vídeos enquanto estiverem no valor
  padrão; o botão **Padrão** ao lado de cada uma refaz o caminho a qualquer
  momento, e nada impede apontar para outro lugar.
- **Gerar thumbnails**: desmarcado, o programa vai direto para a revisão usando as
  thumbs existentes. Marcado, gera antes — com a opção *somente vídeos que ainda
  não têm thumbnail*, que é o caso comum quando você adiciona vídeos novos.
- **Sessão de revisão**:
  - *Revisar todos* — passa por tudo que tem thumbnail;
  - *Verificação randômica* — sorteia N vídeos e a sessão termina neles, para
    fatiar uma pasta grande ao longo de vários dias;
  - *Pular vídeos que já revisei* — usa o histórico para não repetir o que você
    já decidiu em sessões anteriores;
  - *Mostrar em ordem randômica* — embaralha a exibição em vez de seguir o
    alfabeto. Numa pasta onde os nomes agrupam o conteúdo, a ordem alfabética
    faz você ver tudo de um tipo de uma vez;
  - *Vídeos do "talvez"* — **deixar de fora**, **incluir na sessão** (junto com
    os demais) ou **somente eles**, para uma rodada dedicada às dúvidas que
    você já acumulou (veja abaixo).

Sortear *quais* vídeos e escolher em que *ordem* mostrá-los são coisas
separadas: a verificação randômica sorteia a amostra e a exibe em ordem
alfabética, a menos que você também marque a ordem randômica.

Quando existe uma **sessão interrompida** guardada para essas pastas, um painel
alaranjado aparece acima do resumo, com **Retomar** e **Descartar** — veja
"Parar no meio e continuar depois".

O painel de resumo mostra quantos vídeos existem, quantos têm thumbnail, quantos
já foram revisados e quantos entram nesta sessão. Logo abaixo vem o painel de
**volume** — veja a seção "Quanto vai sobrar".

### 2. Tela de revisão

Uma thumbnail por vez, ocupando a janela, com a lista da sessão à direita.

As teclas padrão ficam agrupadas à esquerda, para revisar com uma mão só:

| Tecla | Ação |
|---|---|
| `A` ou `←` | vídeo anterior (dá para voltar e trocar a decisão) |
| `D`, `→` ou `Espaço` | próximo vídeo, sem decidir |
| `E` | marca para manter e avança |
| `W` | marca como *talvez* — rever depois — e avança |
| `Q` ou `Del` | marca para apagar e avança |
| `G` | abre o vídeo no player padrão do sistema |
| `Z` ou clique | alterna entre ajustar à janela e zoom 1:1 |
| `Enter` | aplica as decisões e encerra a sessão |

O botão **Atalhos…**, na tela inicial, troca as teclas de cada ação — a escolha
fica salva no `config.json`. As alternativas da tabela (`←`, `→`, `Espaço`,
`Del`) continuam valendo, e `Enter` não é remapeável.

Nada é movido enquanto você decide — as marcações só são aplicadas em **Aplicar e
finalizar** (ou no fim da sessão, que pergunta), sempre com confirmação. Ao lado
dele, **Salvar e sair** guarda a sessão para outro dia sem mover nada.

### 3. O "talvez"

Para o vídeo que a thumbnail não resolve — precisa assistir um trecho, comparar
com outro, decidir com a cabeça mais fria. `W` manda para a pasta *talvez* em vez
de decidir na hora.

O que separa o *talvez* de uma decisão: ele **não entra no histórico como
revisado**. Com *incluir na sessão*, esses vídeos voltam a aparecer nas próximas
sessões junto com os novos, sem você mexer em campo nenhum. Quando finalmente
decidir:

- **manter** devolve o vídeo à pasta de vídeos e aí sim registra como revisado;
- **apagar** manda para a quarentena, como qualquer outro;
- **talvez** de novo deixa onde está, para a próxima rodada.

A opção *somente eles* existe para a outra ponta desse ciclo: uma sessão inteira
feita das dúvidas acumuladas, sem nenhum vídeo novo no meio. É o momento de
sentar e resolver a pilha — comparar os parecidos, abrir no player o que a
thumbnail não resolve — em vez de adiar cada um de novo. Vale combinar com a
verificação randômica quando a pilha ficou grande demais para uma sentada.

### 4. O que acontece ao aplicar

- Vídeos marcados como *apagar* são **movidos** para a pasta de descartes (nunca
  apagados); nomes repetidos ganham sufixo `(2)`, `(3)`… em vez de sobrescrever.
- A **thumbnail continua** na pasta de thumbs, para você reavaliar o descarte
  pela imagem antes de apagar de vez.
- Cada movimento é registrado em `_movimentos.jsonl` (origem, destino, data e
  motivo), dentro da pasta de destino — ou da pasta *talvez*, no caso de uma
  devolução, para não largar arquivo de log na sua pasta de vídeos.
- Um movimento que falha (permissão, disco cheio) **não** é registrado no
  histórico: o vídeo volta a aparecer na próxima sessão, com a decisão a tomar
  de novo.

### 5. Quanto vai sobrar

A pergunta que o painel de volume responde: *em que tamanho esta pasta vai
parar quando eu terminar de triar tudo?*

Na tela inicial ele mostra o que a pasta ocupa hoje, o que está no *talvez*, o
que está parado na quarentena (ainda ocupando disco até você apagar de verdade)
e, com base no histórico:

```
1,8 TB em 2.431 vídeo(s) · 12,4 GB no “talvez” · 210,5 GB parados na quarentena
Você descarta 43% do volume que decide (612 vídeos decididos, 890,0 GB).
Faltam decidir 1,1 TB — nesse ritmo, devem sobrar 1,3 TB no fim do processo.
```

A conta é direta: a fração de **bytes** que você mandou para a quarentena, entre
tudo que já decidiu, aplicada ao volume que ainda falta decidir. Não é a fração
de *arquivos* — descartar dez clipes de 20 MB não diz o mesmo que descartar um
arquivo de 8 GB, e o que interessa aqui é o disco.

Na tela de revisão a mesma linha acompanha a sessão: quanto você já marcou para
apagar, para o *talvez* e para manter, com a projeção reagindo a cada decisão —
inclusive às desta sessão, antes mesmo de aplicar.

A taxa só aparece depois de **5 vídeos decididos com o tamanho registrado**;
antes disso ela seria 0% ou 100%. Como o tamanho passou a ser gravado no
histórico só a partir desta versão, as decisões que você tomou antes não entram
na conta — a projeção começa a valer depois das próximas sessões.

### 6. Parar no meio e continuar depois

Uma pasta com milhares de vídeos não cabe numa sentada, e a interrupção não
avisa. Há duas formas de largar a sessão pela metade, para dois problemas
diferentes.

**Aplicar e continuar outro dia.** Aperte `Enter`, aplique, e pronto: os vídeos
decididos entram no histórico e *Pular vídeos que já revisei* os deixa de fora
das próximas sessões. Pode re-randomizar à vontade — o que você já viu não
volta. Fechar a janela com decisões pendentes oferece **Aplicar e sair**, que
faz exatamente isso sem exigir que você lembre do `Enter`.

**Guardar a sessão inteira.** É o que a *verificação randômica* pede: aplicar no
meio encerra aquele sorteio, e os vídeos que você ainda não viu voltam para o
bolo — talvez nunca mais caindo juntos. **Salvar e sair** congela a sessão como
ela está: a lista sorteada, as marcações que você já fez e a posição em que
parou. Na próxima abertura, **Retomar** devolve tudo, inclusive as cores na
lista lateral, e você segue do vídeo seguinte ao último decidido.

Não é preciso lembrar de salvar: **cada decisão grava a sessão em disco**. Se o
programa morrer, a máquina desligar ou você fechar a janela no susto, a sessão
está lá na volta. O arquivo é pequeno e some sozinho quando você aplica.

Entre salvar e retomar o mundo pode ter mudado, e a retomada lida com isso:

- vídeo apagado ou movido para fora das pastas → sai da sessão, com aviso de
  quantos ficaram de fora, e a posição salva acompanha o encurtamento;
- vídeo que trocou de pasta (do *talvez* para os vídeos, por exemplo) →
  reencontrado pelo nome, com a origem corrigida;
- **iniciar uma sessão nova** com uma salva pendente → o programa pergunta
  antes, porque isso descarta as marcações guardadas.

Só há uma sessão salva por pasta de thumbnails, e ela é oferecida apenas quando
a pasta de vídeos é a mesma de quando foi salva. Sair sem ter decidido nada não
salva nada — não há o que preservar numa sessão em que você só navegou.

## Arquivos de estado

| Arquivo | Onde | Para quê |
|---|---|---|
| `.video_manager_state.json` | pasta de thumbnails | histórico de decisões, com o tamanho de cada vídeo (alimenta o "pular já revisados" e a projeção de volume; o *talvez* fica registrado, mas não conta como revisado) |
| `.video_manager_session.json` | pasta de thumbnails | sessão interrompida: lista, marcações não aplicadas e posição (some ao aplicar) |
| `_movimentos.jsonl` | pastas de descartes e de *talvez* | log dos vídeos movidos |
| `config.json` | `~/.config/video_manager/` | últimas pastas, opções usadas e atalhos |

O histórico fica junto das thumbs de propósito: se a pasta mudar de lugar ou de
máquina, ele vai junto.

## Nota sobre abrir o vídeo no player (tecla `G`)

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
├── library.py     varredura, pareamento vídeo↔thumb, sessão salva, quarentena
├── thumbs.py      extração dos frames e montagem da grade (motor do notebook)
├── worker.py      geração em thread separada
├── ui_setup.py    tela inicial
├── ui_review.py   tela de revisão
└── app.py         janela principal
```
