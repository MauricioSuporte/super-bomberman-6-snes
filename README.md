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
| Tela de título: abertura do jogo Unity (câmera subindo, personagens caindo do centro para fora, logo descendo), logo com as cores animadas e troca ocasional de pose dos personagens | pronto (Start/A pula; voltando de um menu a abertura não repete; com o som da câmera e das quedas dos personagens; sem os pequenos deslocamentos das poses alternadas) |
| Tela de título: opções entre logo e personagens, versão no rodapé | pronto (`version_text` em `assets/title/convert.json`) |
| Tela de título: cursor do SB6 (`assets/title/Cursor.png`) | pronto: cabeça com o rosto do jogo Unity; depois de 3 s sem apertar nada ele olha para os lados ou para cima/baixo com um rosto sorteado; ao confirmar (A/Start) faz o aceno de confirmação e fica com o rosto de confirmação (sem o pulinho do cursor do SB5). As animações de "opção negada" e de apagar o progresso do Unity não existem neste menu |
| Tela de título: música do SB6 (streaming BRR) | pronto; SFX do menu tocam junto com ela |
| SFX de menu do SB6 (mover cursor, confirmar, voltar) | pronto no título e nos menus (Normal, Battle, senha...); durante as fases, onde a música ocupa a memória de som, continuam os bipes do SB5 |
| SFX das fases: encurralado, morte do jogador, morte do inimigo | pronto: quando o jogador fica preso com uma bomba (animação $21) toca `assets/sound/cornered.wav` (do jogo Unity, 8,4 kHz); a morte do jogador toca o som do Super Bomberman 1 **na hora** (o SB5 transferia a voz para a memória de som durante ~0,5 s antes de tocar); a morte de inimigo toca a do Super Bomberman 1 no instante em que o inimigo é atingido (o som do SB5 só vinha ~1 s depois, junto com a pontuação, e agora fica mudo). Os sons do SB1 são os samples originais (`tools/extract_sb1_sfx.py` copia da ROM do SB1 para `assets/sound/sb1_*.brr`) tocados com as mesmas notas. Nas músicas 15, 16, 21, 23, 24 e 25 (fora das fases) o som de encurralado sai cortado |
| Normal Game para 3-4 jogadores (multitap na porta 2) | pronto: escolha em NORMAL GAME → 1-4 PLAYER GAME; P3 vermelho no canto inferior esquerdo, P4 azul no inferior direito; vidas compartilhadas, Start para voltar; ovos e Louies usam páginas de sprite livres da fase (nas 8 fases sem espaço sobrando ainda podem aparecer embaralhados) e mantêm as cores (se faltar paleta, P3/P4 usam as cores do P1 por alguns instantes). Nas lutas contra chefes o rival fica no slot do P5 e os 4 jogadores lutam (P3 nasce à esquerda do P1, P4 à direita do P2); só na ZONE3-D (dois rivais) o P4 fica de fora e volta na fase seguinte com seus itens |
| Seleção de personagem e cor no Normal Game | pronto: depois de escolher o arquivo (New Game ou Continue) abre a tela CHARACTER SELECT no estilo do SB6 Unity: retratos de `assets/picker/CharacterSelectPortrait.png` (o de baixo do cursor troca para a 2ª linha, com as cores da skin escolhida), cursor de `SkinSelectCursor.png` com **L / R** em cima e o número do jogador embaixo, na cor da skin; **um jogador escolhe por vez** (P1, depois P2...); **R**/**L** trocam a cor (com som `assets/sound/menu_palette.wav`); **A** confirma (se outro jogador já pegou o mesmo personagem com a mesma cor, não deixa), **B** desfaz a escolha do jogador anterior ou, no P1, volta para a lista de arquivos. Em cima fica a fileira dos jogadores (cursores P1-P4 do Unity): quem está escolhendo aparece andando para baixo (animação 02) meio apagado, quem já escolheu faz a animação 20 uma vez e fica parado no último quadro. A escolha vale para a campanha toda |
| Paletas dos sprites: jogadores com 15 cores, Louies e ovos em paleta própria | pronto: uma paleta de sprite guarda até 2 cores de Louie (8 cores cada, o contorno é comum) e todos os Louies da mesma cor a dividem; o ovo usa as cores do Louie rosa, então só aparece se houver uma metade livre (ou já com o rosa) ou uma paleta livre só para ele; com as 2 metades ocupadas, o Louie que nasce vira um dos 2 que já existem; morrer não troca mais as cores do jogador. Falta tratar chefes e fases que usam mais paletas (zona 5) |
| Mapa da ZONE1 (world map) | pronto: ilha, nuvens, prédios e a torre central do mapa do World 1 do Super Bomberman 1, com o mar animado como no SB1 (o tile da água troca de quadro a cada 12 frames; as nuvens do SB1 são paradas); mantidos a placa START e as marcações das fases do SB5 (ainda nas posições do SB5). Música: a do mapa do SB1, tocada pelo próprio driver de som do SB1 (a memória de som do SB1 é enviada ao entrar no mapa, ~1 s de tela preta a mais; ao sair, o driver do SB5 é recarregado como no boot). No mapa, mover toca o som de menu do SB1 e confirmar (escolher a fase) toca o confirmar do SB6 sem parar a música; outros SFX ficam mudos. Assets em `assets/world_map/` e `assets/sound/sb1_world_map.bin` (`tools/extract_world_map.py` + `tools/mesen/sb1_world_map.lua`). As zonas 3 em diante continuam como no SB5 |
| Mapa da ZONE2 (world map) | pronto: o mapa do World 1 do Super Bomberman 2 (naves no BG, estrelas descendo meia linha por frame como no SB2, luzes das naves piscando no ciclo de 64 frames do SB2); mantidas as marcações das fases do SB5. Algumas cores onde as naves se sobrepõem usam a cor mais próxima (limite de paletas). Música: a do mapa do SB2, tocada pelo driver de som do SB2. Trocar de zona com L/R agora troca o driver de som (SB1 ⇄ SB2 ⇄ SB5), ~1-1,5 s de tela escura na troca. Assets `assets/world_map/zone2_*` e `assets/sound/sb2_world_map*.bin` (`tools/extract_world_map.py zone2` + `tools/mesen/sb2_world_map.lua`) |
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

Os outros nove personagens da seleção têm cada um três arquivos em
`assets/bombers` (o número é a posição na grade do CHARACTER SELECT, contando
a partir do vizinho do Bomberman):

* `charN_sb6.png`: a folha para editar. Tem o mesmo layout do
  `bomber_sb6.png` (mesmas animações, mesmas poses, mesmas sequências, como o
  andar 12321454) e começa como uma cópia dele;
* `charN_sb5.png`: a arte do SB5 desse personagem, só de referência (o build
  não lê);
* `charN_pallete.png`: no mesmo formato do `BombermanPallete.png` (começa como
  uma cópia dele). A 1ª coluna são as cores-chave do Bomberman, e as outras
  colunas são as cores que o L / R escolhe (todas, não só seis). Pinte a
  folha com as cores do `bomber_sb6.png`. Também pode ser uma paleta com
  cores-chave próprias (por exemplo a de 44 colunas com linhas a mais, como
  nos chars 4, 5 e 6): aí a folha é pintada com a 1ª coluna dessa imagem.
  Um sprite de SNES tem só 15 cores; se a folha usar mais, o build junta as
  menos usadas com a cor mais parecida e lista no final quais juntou.
  Personagens com a mesma imagem de paleta dividem as mesmas cores na ROM.

Todo personagem com folha entra no jogo e na grade da seleção com a arte do
SB6, mesmo que a folha ainda seja igual à do Bomberman: é só editar a folha e
rodar o build. A paleta e os tiles iguais aos do Bomberman são reaproveitados
(não são duplicados na ROM). As animações que você não mexer
usam os tiles do Bomberman (não gastam ROM), e só as editadas ganham tiles
novos. `charN_anims.txt` (opcional) troca só as sequências que forem
diferentes das do `bomber_anims.txt`. Quando as poses de uma animação passam
de 32 tiles 8x8 juntas (personagem mais alto ou mais largo que o Bomberman),
o build manda cada pose separada para a VRAM na hora em que ela aparece; aí o
limite passa a ser por pose: 16 tiles (até 32x32 px). O `check` lista essas
animações. Para aparecer na grade
da seleção o personagem precisa de uma coluna em
`assets/picker/CharacterSelectPortrait.png` (hoje 7: personagens 0-6; os 7-9
ficam de fora da grade). Na fileira de cima da seleção cada pose das
animações 02 e 20 tem que caber em 8 sprites de 16x16.
A altura da bomba erguida com a luva azul (Power Glove) segue a cabeça de
cada personagem: o build compara o topo das poses com a bomba (animações
`2F-3A`) com as do Bomberman (personagem mais baixo = bomba mais baixa).

```
python tools/bomber_sheet.py export --edit   # recria as referências *_sb5.png e os editáveis que não existirem
python tools/bomber_sheet.py template 3 --force   # volta o personagem 3 para a cópia do Bomberman
python tools/bomber_sheet.py labels         # reescreve a coluna de rótulos com as sequências atuais
python tools/bomber_sheet.py check           # confere as folhas sem gerar a ROM
python tools/build.py                        # insere as folhas no jogo
```

Para conferir um personagem novo no Mesen (andar nas 4 direções e a
animação 21, de quando ele fica encurralado por uma bomba), use
`tools/mesen/walk_capture.lua` (`TEST=walk` ou `TEST=trap`) e
`tools/walk_check.py`; o passo a passo está na skill
`.claude/skills/sb6-character/SKILL.md` (peça ao Claude "vamos fazer o char2").

### 7. Jogue

Abra `build/Super Bomberman 6.sfc` num emulador (Mesen 2, bsnes, snes9x) ou
grave num cartucho repro HiROM de 32 Mbit. Para 3 ou 4 jogadores, ligue um
multitap (Super Multitap) na **porta 2**.

### Saídas em `build/`

* `Super Bomberman 6.sfc`: a ROM (4 194 304 bytes, checksum corrigido)
* `sb6.map`: mapa de tudo que foi alocado e de cada byte original alterado
* `title_preview.png`: quadros da abertura e das poses alternadas do título, desenhados a partir das mesmas tabelas que a ROM usa (o build falha se alguma etapa não sair como foi composta)
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
assets/              logo de abertura (HU3DSON LOGO.png), sons do fan game (sound/)
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
