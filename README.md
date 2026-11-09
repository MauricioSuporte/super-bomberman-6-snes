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
| Normal Game para 3-4 jogadores (multitap na porta 2) | pronto: escolha em NORMAL GAME → 1-4 PLAYER GAME; P3 vermelho no canto inferior esquerdo, P4 azul no inferior direito; vidas compartilhadas, Start para voltar; ovos e Louies usam páginas de sprite livres da fase (nas 8 fases sem espaço sobrando ainda podem aparecer embaralhados) e mantêm as cores (se faltar paleta, P3/P4 usam as cores do P1 por alguns instantes). P3/P4 ficam de fora das lutas contra chefes |
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
