# super-bomberman-6-snes

ROM hack **Super Bomberman 6** para Super Nintendo, construído a partir de
*Super Bomberman 5 (USA)* com gráficos e músicas do fan game
[Super-Bomberman-6-Unity](https://github.com/MauricioSuporte/Super-Bomberman-6-Unity)
(branch `v0.5.0`). O conhecimento sobre o jogo original vem em grande parte da
[SuperBomberman5SNESRecomp](https://github.com/MauricioSuporte/SuperBomberman5SNESRecomp).

A ROM gerada mantém **exatamente 4 MB, HiROM**, como a original, para poder
ser gravada num cartucho repro e rodar no hardware real.

## Estado atual

| Parte | Situação |
|---|---|
| Abertura: logo HU3DSON (`assets/HU3DSON LOGO.png`) e ida direta ao título, sem a intro do SB5 | pronto (a intro do SB6 virá depois) |
| Tela de título: fundo, personagens e logo do SB6 | pronto |
| Tela de título: opções entre logo e personagens, versão no rodapé | pronto (`version_text` em `assets/title/convert.json`) |
| Tela de título: música do SB6 (streaming BRR) | pronto; SFX do menu (mover/confirmar) tocam junto com ela |
| Normal Game para 3-4 jogadores (multitap na porta 2) | pronto: escolha em NORMAL GAME → 1-4 PLAYER GAME; P3 vermelho no canto inferior esquerdo, P4 azul no inferior direito; vidas compartilhadas, Start para voltar; ovos e Louies usam páginas de sprite livres da fase (nas 8 fases sem espaço sobrando ainda podem aparecer embaralhados) e mantêm as cores (se faltar paleta, P3/P4 usam as cores do P1 por alguns instantes). Nas lutas contra chefes o rival fica no slot do P5 e os 4 jogadores lutam (P3 nasce à esquerda do P1, P4 à direita do P2); só na ZONE3-D (dois rivais) o P4 fica de fora e volta na fase seguinte com seus itens |
| Paletas dos sprites: jogadores com 15 cores, Louies e ovos em paleta própria | pronto: uma paleta de sprite guarda até 2 cores de Louie (8 cores cada, o contorno é comum) e todos os Louies da mesma cor a dividem; o ovo usa as cores do Louie rosa, então só aparece se houver uma metade livre (ou já com o rosa) ou uma paleta livre só para ele; com as 2 metades ocupadas, o Louie que nasce vira um dos 2 que já existem; morrer não troca mais as cores do jogador. Falta tratar chefes e fases que usam mais paletas (zona 5) |
| Demais telas, fases, inimigos, chefes, músicas | originais do SB5 |

## Como gerar a ROM (passo a passo)

A ROM do SB6 **não é distribuída**: ela é gerada na sua máquina a partir da
ROM original do SB5 mais os arquivos deste repositório. Os passos abaixo são
para Windows (os comandos usam o PowerShell ou o Prompt de Comando).

### 1. Instale o Python

1. Baixe o Python 3.12 (ou mais novo) em <https://www.python.org/downloads/>.
2. Na instalação, marque **"Add python.exe to PATH"**.
3. Confira num terminal novo:
   ```
   python --version
   ```

### 2. Baixe o repositório

Com o Git instalado:
```
git clone https://github.com/MauricioSuporte/super-bomberman-6-snes.git
cd super-bomberman-6-snes
```
(ou baixe o ZIP pelo GitHub e extraia; os passos seguintes são feitos dentro
dessa pasta).

### 3. Instale as bibliotecas Python

```
python -m pip install -r requirements.txt
```
Isso instala numpy, Pillow e scipy.

### 4. Instale o asar (assembler do SNES)

1. Baixe o **asar 1.91** em <https://github.com/RPGHacker/asar/releases>
   (arquivo `asar191.zip`).
2. Extraia em `D:\sb6-tools\asar\`, de modo que exista
   `D:\sb6-tools\asar\asar.exe`.
3. Se preferir outra pasta, informe o caminho pela variável `SB6_ASAR`:
   ```
   $env:SB6_ASAR = "C:\caminho\para\asar.exe"      # PowerShell
   set SB6_ASAR=C:\caminho\para\asar.exe           # Prompt de Comando
   ```

### 5. Coloque a ROM original

Copie a sua ROM de *Super Bomberman 5 (USA)* para a raiz do repositório com
o nome exato:
```
Super Bomberman 5 (USA).sfc
```
Ela precisa ser a versão sem header e sem modificações (4 194 304 bytes,
sha1 `417d5ace7e51baafb69d20ce15ff0894d91c70c5`). O build confere o sha1 e
para com erro se for outra. Essa ROM está no `.gitignore` e nunca deve ser
enviada ao repositório.

### 6. Gere a ROM

```
python tools/build.py
```
A primeira vez demora cerca de 1 minuto (a música do título é convertida para
BRR e guardada em `build/cache/`); as seguintes levam poucos segundos. Ao
final aparece `wrote ...\build\Super Bomberman 6.sfc (4194304 bytes)`.

Opções: `--base caminho.sfc` usa outra cópia da ROM original; `--out pasta`
muda a pasta de saída; `--search` testa várias quantizações de paleta do
título e mostra a melhor (lento; o resultado vai em
`assets/title/convert.json`).

### Sprites do Bomberman (folha de poses)

`assets/bombers/bomber.png` é a folha editável do jogador: cada célula de
64x64 é uma pose já montada, cada linha é uma animação (o rótulo traz o número,
a direção e a ordem em que as poses tocam). Esquerda e direita são células
separadas, então não precisam ser espelhadas. Regras: não mude o tamanho da
imagem, pinte só dentro das células, fundo transparente (ou magenta `FF00FF`),
use as 8 cores mostradas no topo. A grade é a mesma do `Bomberman.png` do
projeto Unity (64x64, personagem no mesmo lugar da célula: centro em x=32, sola
na linha 43), então dá para copiar quadro a quadro; a 1ª coluna de cada bloco
é só rótulo. Linhas marcadas `+8px abaixo` têm o personagem 8 px mais baixo
na célula (poses que sobem acima dela). Todas as poses de uma mesma linha dividem 32
tiles de 8x8 (peças iguais ou espelhadas contam uma vez).

Arte do SB6: se existirem `assets/bombers/bomber_sb6.png` (a mesma folha,
pintada com as cores da 1ª coluna de `BombermanPallete.png`) e
`BombermanPallete.png` (1 pixel por cor; colunas 2-5 = branco, preto, vermelho,
azul), o build usa essa folha e troca as paletas dos quatro Bombermans. O
limite do SNES é de 15 cores por sprite; células ainda iguais às do SB5 são
repintadas com as cores mais próximas.

A ordem das poses de cada animação fica em `assets/bombers/bomber_anims.txt`
(uma linha por animação: número, quadros por pose, sequência de células; `[`
marca onde o loop recomeça e `fim` faz o personagem sumir no final). O que
não estiver lá toca como no SB5. Uma animação pode usar até 7 células; as
células que a sequência não usa são ignoradas.

```
python tools/bomber_sheet.py export --edit   # recria bomber_sb5.png (referência) e bomber.png se não existir
python tools/bomber_sheet.py check           # confere a folha sem gerar a ROM
python tools/build.py                        # insere a folha no jogo
```

### 7. Jogue

Abra `build/Super Bomberman 6.sfc` num emulador (Mesen 2, bsnes, snes9x) ou
grave num cartucho repro HiROM de 32 Mbit. Para 3 ou 4 jogadores, ligue um
multitap (Super Multitap) na **porta 2**.

### Saídas em `build/`

* `Super Bomberman 6.sfc`: a ROM (4 194 304 bytes, checksum corrigido)
* `sb6.map`: mapa de tudo que foi alocado e de cada byte original alterado
* `title_preview.png`: tela de título do jogo Unity comparada com o resultado convertido
* `boot_logo_preview.png`: a logo de abertura convertida
* `cache/`: áudio BRR já codificado

Para ouvir a conversão da música sem emulador:
`python tools/brr_preview.py build/cache/title_music_*.brr build/title_music_preview.wav`

### Problemas comuns

| Mensagem | Causa / solução |
|---|---|
| `asar not found at ...; set SB6_ASAR` | asar não está em `D:\sb6-tools\asar\asar.exe`; veja o passo 4 |
| erro de sha1 da ROM base | ROM com header (4 194 816 bytes), outra região ou já modificada; use a USA original |
| `No module named numpy` (ou PIL/scipy) | refaça o passo 3 com o mesmo `python` que roda o build |
| `... holds xx, expected yy` | a ROM base não é a original, ou um patch tem endereço errado |

## Organização

```
assets/title/        imagens, layout e música vindos do fan game
assets/bombers/      folha de poses do Bomberman (bomber.png) e a referência do SB5
assets/              logo de abertura (HU3DSON LOGO.png), SFX capturados (sound/)
asm/                 código 65816 (asar)
asm/spc/             código SPC700 (asar)
tools/build.py       ponto de entrada do build
tools/sb6/           biblioteca: ROM, compressão, gráficos, BRR, asar
tools/sb6/features/  uma feature por arquivo (title.py, title_music.py, ...)
tools/disasm65816.py desmontador 65816      tools/spc700dis.py desmontador SPC700
tools/scriptdis.py   desmontador dos scripts do jogo (VM de $C2)
docs/ROM_MAP.md      o que se sabe da ROM do SB5 (formatos, rotinas, hooks)
docs/FREE_SPACE.md   espaço livre na ROM, WRAM e ARAM, e quem usa o quê
```

Regras do projeto (resumo de [CLAUDE.md](CLAUDE.md)): a ROM sempre sai da
original + fontes; todo byte original alterado passa por `patch()`, que
confere o conteúdo antigo; dados novos só entram por `alloc()` em regiões
livres verificadas; cada descoberta vai para `docs/`.

## Sprites e paletas do Bomberman

Arquivos em `assets/bomberman/` (extraídos da ROM com
`python tools/extract_bomberman.py ROM.sfc`):

* `sheet.png` — PNG indexado 128x224, as duas folhas de tiles do Bomberman
  (arquivos `$01` em cima, `$02` embaixo da linha vermelha do guia). Edite
  pixel por pixel mantendo o modo indexado; índice 0 = transparente. Use os
  índices 1-7 (no SB5 o 8 era trocado pela cor do Louie montado; hoje o
  Louie tem paleta própria).
  Cada quadro é montado a partir de blocos 8x8/16x16 nessas posições: mude
  o desenho, não a posição.
* `palettes.png` — 7 linhas (as 7 cores do Bomberman: branco, preto,
  vermelho, azul, verde...) x 9 quadrados 16x16 (índices 0-8). Troque as cores.
* `guide.png` — só referência (ampliado, grade 16x16 e número do tile).

O `build.py` reconverte os PNGs e só altera os bytes que mudaram.
