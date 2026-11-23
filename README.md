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
| Tela de título: OPTIONS vira um submenu do SB6 | pronto: OPTIONS confirma como as outras opções (som de confirmar + animação do cursor) e mostra o submenu com **DISCORD**; DISCORD abre um QR Code com o convite do servidor do Super Bomberman 6 (https://discord.gg/cjQxEBMrRa, imagem em `assets/options/discord_qr.png`); qualquer botão fecha o QR e volta ao submenu; **B** no submenu volta ao menu com o cursor em OPTIONS. Com o submenu/QR aberto a demo automática não começa. As telas Options, Sound Test e Password do SB5 foram removidas da ROM (scripts, gráficos, música da senha: ~15 KB liberados) |
| Tela de título: música do SB6 (streaming BRR) | pronto; SFX do menu tocam junto com ela |
| SFX de menu do SB6 (mover cursor, confirmar, voltar) | pronto no título e nos menus (Normal, Battle...); durante as fases, onde a música ocupa a memória de som, continuam os bipes do SB5 |
| SFX das fases: encurralado, morte do jogador, morte do inimigo | pronto: quando o jogador fica preso com uma bomba (animação $21) toca `assets/sound/cornered.wav` (do jogo Unity, 8,4 kHz); a morte do jogador toca o som do Super Bomberman 1 **na hora** (o SB5 transferia a voz para a memória de som durante ~0,5 s antes de tocar; a voz do SB5 foi apagada da ROM); a morte de inimigo toca a do Super Bomberman 1 no instante em que o inimigo é atingido (o som do SB5 só vinha ~1 s depois, junto com a pontuação, e agora fica mudo). Os sons do SB1 são os samples originais (`tools/extract_sb1_sfx.py` copia da ROM do SB1 para `assets/sound/sb1_*.brr`) tocados com as mesmas notas. Todos os outros sons das fases são os do SB5 (plantar bomba, explosão, Louie...). O som de encurralado sai cortado nas músicas 15, 16, 21, 23, 24 e 25 (fora das fases) e nas músicas do SB1 das fases 1-1 a 1-3 |
| Normal Game para 3-4 jogadores (multitap na porta 2) | pronto: escolha em NORMAL GAME → 1-4 PLAYER GAME; P3 vermelho no canto inferior esquerdo, P4 azul no inferior direito; todo jogador nasce com espaço garantido para soltar uma bomba e se esconder (o jogo reserva esse caminho livre de blocos) e sem inimigo a menos de 6 casas (`tools/coop4_check.py` valida em todas as fases); vidas compartilhadas, Start para voltar; ovos e Louies usam páginas de sprite livres da fase (nas 8 fases sem espaço sobrando ainda podem aparecer embaralhados) e mantêm as cores (se faltar paleta, P3/P4 usam as cores do P1 por alguns instantes). Nas lutas contra chefes o rival fica no slot do P5 e os 4 jogadores lutam (P3 nasce à esquerda do P1, P4 à direita do P2); só na ZONE3-D (dois rivais) o P4 fica de fora e volta na fase seguinte com seus itens |
| Seleção de personagem e cor no Normal Game | pronto: depois de escolher o arquivo (New Game ou Continue) abre a tela CHARACTER SELECT no estilo do SB6 Unity: retratos de `assets/picker/CharacterSelectPortrait.png` (o de baixo do cursor troca para a 2ª linha, com as cores da skin escolhida), cursor de `SkinSelectCursor.png` com **L / R** em cima e o número do jogador embaixo, na cor da skin; **um jogador escolhe por vez** (P1, depois P2...); **R**/**L** trocam a cor (com som `assets/sound/menu_palette.wav`); **A** confirma (se outro jogador já pegou o mesmo personagem com a mesma cor, não deixa), **B** desfaz a escolha do jogador anterior ou, no P1, volta para a lista de arquivos. Em cima fica a fileira dos jogadores (cursores P1-P4 do Unity): quem está escolhendo aparece andando para baixo (animação 02) meio apagado, quem já escolheu faz a animação 20 uma vez e fica parado no último quadro. A escolha vale para a campanha toda |
| Paletas dos sprites: jogadores com 15 cores, Louies e ovos em paleta própria | pronto: uma paleta de sprite guarda até 2 cores de Louie (8 cores cada, o contorno é comum) e todos os Louies da mesma cor a dividem; o ovo usa as cores do Louie rosa, então só aparece se houver uma metade livre (ou já com o rosa) ou uma paleta livre só para ele; com as 2 metades ocupadas, o Louie que nasce vira um dos 2 que já existem; morrer não troca mais as cores do jogador. Falta tratar chefes e fases que usam mais paletas (zona 5) |
| Mapa da ZONE1 (world map) | pronto: ilha, nuvens, prédios e a torre central do mapa do World 1 do Super Bomberman 1, com o mar animado como no SB1 (o tile da água troca de quadro a cada 12 frames; as nuvens do SB1 são paradas); mantidos a placa START e as marcações das fases do SB5 (ainda nas posições do SB5). Música: a do mapa do SB1, tocada pelo próprio driver de som do SB1 (a memória de som do SB1 é enviada ao entrar no mapa, ~1 s de tela preta a mais; ao sair, o driver do SB5 é recarregado como no boot). No mapa, mover toca o som de menu do SB1 e confirmar (escolher a fase) toca o confirmar do SB6 sem parar a música; outros SFX ficam mudos. Assets em `assets/world_map/` e `assets/sound/sb1_world_map.bin` (`tools/extract_world_map.py` + `tools/mesen/sb1_world_map.lua`). As zonas 3 em diante continuam como no SB5 |
| Mapa da ZONE2 (world map) | pronto: o mapa do World 1 do Super Bomberman 2 (naves no BG, estrelas descendo meia linha por frame como no SB2, luzes das naves piscando no ciclo de 64 frames do SB2); mantidas as marcações das fases do SB5. Algumas cores onde as naves se sobrepõem usam a cor mais próxima (limite de paletas). Música: a do mapa do SB2, tocada pelo driver de som do SB2. Trocar de zona com L/R agora troca o driver de som (SB1 ⇄ SB2 ⇄ SB5), ~1-1,5 s de tela escura na troca. Assets `assets/world_map/zone2_*` e `assets/sound/sb2_world_map*.bin` (`tools/extract_world_map.py zone2` + `tools/mesen/sb2_world_map.lua`) |
| Fases do WORLD 1 | em andamento. Feito: "ZONE" virou "WORLD" no mapa (e "STAGE 1-1" no início das fases); cadeia de 7 fases (1-1 = SB5 1-1, 1-2 = SB5 1-5, 1-3 = SB5 1-12, 1-4 = SB1 4-4, 1-5 = SB1 6-4, 1-6 = torneio do SB6 (3 duelos), 1-7 = arena SB1 4-8; depois vai para o 2-1); porta de saída no estilo SB1 escondida num bloco, que aparece quando todos os inimigos morrem (bombardear a porta não gera inimigos; sem porta em 1-6; no 1-7 ela aparece no chão quando o palhaço morre); fases no driver de som do SB5 (sons do SB5, só as mortes do jogador, dos rivais e de inimigo são do SB1); a 1-1 toca a música do World 1 do SB1, a 1-2 a do World 2, a 1-3 a do World 3, a 1-4 a do World 4 e a 1-5 a do World 6 (da 1-1 à 1-5, as músicas convertidas direto do driver de som do SB1, a partir de logs do Mesen; as versões feitas dos MIDIs ficam guardadas sem uso) e a 1-6 a do World 5, a partir do MIDI do khinsider (`assets/SB1 midi`: level; `tools/midi_song.py` acha cada trilha no SB1 e usa a altura e o volume exatos do SB1 e os samples do SB1), convertidas para o formato do SB5 (depois do jingle de início do SB5, que continua; a música é carregada junto com a fase, com a tela preta, sem travar o jogo; `tools/sb1_song.py` extrai as notas de um log do SB1, `features/sb1_music.py` monta as músicas; ~30-35 KB na ROM cada; a fase seguinte recarrega a sequência do SB5, o que corrigiu a tela preta ao sair da 1-2), a música da ZONE1 do SB5 não é mais usada e os samples exclusivos dela foram removidos da ROM (~7,2 KB livres em `$DC`); gráficos das fases 1-4 / 1-5 / 1-6 / 1-7 tirados do SB1 (`assets/stages/`, `tools/sb1_stage_assets.py`, `features/sb1_stages.py`); 1-5 só com os 2 cavaleiros do 6-4, com 2 de vida, que não levam dano de explosão vinda da frente (se virarem no meio da explosão, levam); blocos queimando com os quadros do próprio SB1 (bumper afundando na 1-4, bloco se desfazendo na 1-5); bordas da 1-5 sem a animação do SB5 que trocava os tiles; dados da ZONE1 do SB5 sem uso liberados; 1-2 com os inimigos do SB1 2-1 (2 cabeças de mola, 2 potes, 2 palhaços, nas casas onde o SB1 os põe; o SB1 tem 4 molas, 2 ficaram de fora para 4 jogadores não perderem velocidade; `assets/enemies/`, `features/sb1_enemies.py`): todos os quadros e tempos das animações tirados das tabelas da ROM do SB1 (`tools/sb1_enemy_frames.py`; a mola estica e encolhe em cada direção, a animação recomeça a cada virada como no SB1) e o comportamento das rotinas do SB1 (`asm/sb1_enemies.asm`): meio pixel por quadro, um inimigo não atravessa o outro (volta e às vezes dá meia-volta), a mola na parede vira para o lado do jogador vivo mais próximo, o pote troca de direção ao acaso a cada 16-79 quadros e atravessa blocos, o palhaço dá meia-volta na parede e a cada 3-6 paredes vira 90°; o toque que mata continua o do SB5 (8 px, no SB1 eram 12); pote e palhaço dividem uma paleta (cores juntadas em 15) para sobrar o slot dos Louies com 4 jogadores; 1-4 com os 2 tanques do SB5 (já existiam no ZONE1-4) mais os 4 OVNIs e o robô-bomba do SB1 4-4, e os blocos (bumpers verdes) animados como no SB1 (luzes girando, 5 quadros); explosões das fases do SB1 sem o fundo verde do SB5 (na 1-6 os primeiros 16 tiles das chamas são enviados 1 s depois do início da fase: o SB5 os reescrevia depois da nossa cópia e deixava quadrados laranja/ciano nas pontas das explosões; e os pixels de sombra da grama do SB5 nas bordas das chamas, que saíam cinza/marrom, viraram o chão da arena); 1-3 com os camaleões do SB1 3-6 (7 com 1-2 jogadores, 6 com 3, 5 com 4, para não perder velocidade), com o comportamento do SB1 (rotina `$C6:69FB` da ROM do SB1, conferida quadro a quadro no Mesen): andam 192-255 quadros, param e se transformam (63 quadros parados, depois piscam entre sapo e cópia com os tempos da tabela do SB1 e trocam de vez logo após as piscadas, sem a pausa de 32 quadros do SB1), e andam disfarçados de um jogador vivo com a animação de caminhar do personagem dele (todas as direções, cores dele), não com o sprite atual do jogador; o fogo mata em qualquer forma (no SB1 o disfarçado só piscava e voltava a ser sapo) (`asm/chameleon.asm`, poses em blocos de até 8 colunas na VRAM livre da 1-3, `sb1_enemies.chameleon`). 1-6 = torneio do mundo 5 do SB1 em 3 duelos seguidos (mecha branco, preto e Golden Bomber, todos com o sheet `char5_sb6.png` nas colunas 2, 3 e 21 da paleta; arena da 5-1 do SB1, sem blocos destrutíveis (o rival não planta mais blocos escondidos: isso era a habilidade do personagem 2 do SB5); torcida animada como no SB1 (4 grupos de tiles trocando a cada 16, 24 e 19 quadros); música do mundo 5 do SB1 a partir do MIDI `level.mid` (melodia, baixo, acordes e bateria com os samples do SB1; 12 unidades por linha para o driver não atrasar o jogo com 4 jogadores); antes do Golden a tela pisca 5 vezes alternando torcida e as paredes de pedra da 5-8; como no SB1, o rival entra pelo corredor da arquibancada e desce até o centro com todos parados, e o portão fecha atrás dele; branco 1 bomba, 1 de fogo e velocidade 1, preto 2, 2 e velocidade 2, dourado 3, 3, velocidade 3, 3 vidas e chuta bombas (velocidade 1 = a inicial dos jogadores, cada nível a mais = um patins), nenhum planta minas; os 3 na dificuldade EASY do Battle (a IA do SB5 tem 4 níveis, EASY/NORMAL/HARD/SUPER); a morte deles toca o som de morte do SB1; itens surgem como no SB1 5-1: depois que o rival chega, um a cada 640 quadros (~11 s) numa casa livre ao acaso, até 32 no campo, só bomba, fogo, patins, luva azul, luva vermelha, chute e atravessar bombas (bomba e fogo com o dobro de chance); os 3 duelos acontecem na mesma fase, sem fim de fase entre eles, como no SB1: 1,5 s depois da morte do rival o portão abre e o próximo desce pelo corredor (antes do Golden a arquibancada pisca com os jogadores travados, na última apagada eles voltam ao ponto de início virados para cima, e só depois o portão abre e ele aparece); o mecha branco e o preto não soltam item ao morrer e a morte deles toca a torcida do SB6 da Unity (`assets/sound/audience.wav`, `features/crowd.py`); a fase termina 5 s depois da morte do Golden ou assim que não sobrar item no campo, o Golden solta o chute; itens, bombas e música continuam; só depois do Golden a fase termina e vai para a 1-7 (antes a fase travava: o portal do SB5 nunca aparecia); os jogadores começam virados para cima, para o corredor por onde o rival desce; no fim de cada duelo toca a vitória de chefe do SB5 ("major victory", a mesma de depois da ZONE1-A: o SB5 carrega o set da música de chefe em ~80 quadros com todos parados, e a fase espera os ~7 s do jingle antes de seguir); só toca o jingle de início da fase e logo a música, sem o jingle de chefe do SB5); 1-7 com a cerca elétrica do SB1 4-8 animada como no SB1 (2 quadros trocados a cada 2 frames) e o chefe palhaço do SB1 2-8 refeito com as regras e tabelas da ROM do SB1 (desenhado no BG2 abaixo do HUD com os 23 quadros do SB1 tirados das tabelas da ROM, `tools/sb1_clown_frames.py`): intro como no SB1 (jogadores parados e virados para cima desde o primeiro quadro da fase, antes do fade-in, até a intro liberar os controles, sem entrar na animação de espera 15 do SB5, a arena e os jogadores escurecem aos poucos, o rosto aparece iluminado por uma luz oval em volta dele, com o brilho no olho, e as luzes voltam aos poucos), persegue o jogador vivo mais próximo acelerando aos poucos como no SB1 (mais rápido quando chora), passa por cima das paredes, mata quem encosta (16 px do centro), leva dano de explosão em até 2 casas do centro, aguenta 8 explosões (no SB1 eram 18); a cada acerto fica 96 quadros parado piscando em branco, solta 8 tiros em 8 direções (matam no toque) e muda de expressão pela tabela de estados do SB1; abaixo da metade da vida fica avermelhado (o vermelho do SB1 suavizado, 40%); morto, pisca em branco com explosões e som de explosão por 385 quadros, afunda no chão (todos os quadros aparecem, sem pixels soltos nas pontas) e some, sem a morte de inimigo comum do SB5, sem porta; depois vem o fim de fase com comemoração e a vitória de chefe do SB5 ("major victory") como depois do Golden Bomber na 1-6, e a fase segue para a 2-1; música = a do chefe do SB1 convertida direto do driver de som do SB1 (a versão do MIDI `boss-battle.mid` fica guardada sem uso), sem o jingle de chefe do SB5 depois do jingle de início; sem os blocos invisíveis que o SB5 espalhava na arena); depois da 1-6 a 1-7 fica liberada no mapa também depois de salvar/reiniciar (o fim de fase grava como fase atual a seguinte); depois de um game over ou de voltar ao mapa pelo pause, a fase começa com o número de jogadores escolhido no título (um save podia guardar a marca do título/demo que forçava 1 jogador) |
| Menu de pausa nas fases (Normal Game) | pronto: Start pausa como no SB5 (PAUSE! e o número da fase, agora escrito STAGE 1-4 em vez de WORLD 1 -04, inclusive no chefe 1-7; o texto que aparece no início de cada fase também virou STAGE 1-1, com as mesmas letras) e, embaixo, aparece o menu do SB6 Unity: **RESUME**, **RETURN TO WORLD MAP**, **RETURN TO TITLE**; cima/baixo movem a seta, Start ou A confirmam, B volta (ou retoma o jogo no menu principal). As duas saídas pedem confirmação (RETURN TO WORLD MAP? / RETURN TO TITLE SCREEN?, NO / YES, começando em NO). YES termina a fase pelo caminho do próprio SB5 sem contar a fase como concluída: o mapa mantém vidas, personagens e cores (a tela fica preta ~5 s, o mesmo carregamento de quando o SB5 volta ao mapa depois de uma zona); o título abre direto, sem repetir a abertura. O menu fica dentro de uma moldura laranja/amarela (como a do Unity) com o fundo da fase escurecido e transparente só dentro dela (color math numa janela, linhas por HDMA; a fase vai para a subscreen dentro da janela para escurecer todos os sprites, inclusive os de paletas 0-3 como o tanque); o texto e a moldura ficam por cima. Letras próprias 8x8 e a moldura na VRAM livre do BG3, restauradas ao retomar. Na volta ao mapa não toca mais a música da seleção de save/personagem. No Battle a pausa continua a do SB5; nas lutas da 1-6 o SB5 não tem pausa |
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

### 8. Testes de qualidade (depois de mudar a ROM)

```
python tools/qa_check.py            # tudo menos os lentos (~30 s com a ROM já testada uma vez)
python tools/qa_check.py all        # + desempenho/cantos seguros e explosões (~2 min)
python tools/qa_check.py anims sfx  # só algumas suítes;  --list mostra todas;  -v mostra cada teste
```

Roda o jogo no Mesen 2 sem janela, com 4 jogadores no Normal Game, e confere
sozinho (sem IA): seleção de personagens e cores refletidas na fase, todas as
animações (andar, socar, chutar, levantar/carregar/arremessar nas 4 direções,
ocioso, encurralado, morte, tempo esgotado, vitória, Louies) quadro a quadro
contra a folha de poses de cada personagem, efeitos sonoros (bomba, explosão
por alcance, pierce, soco, quique, chute, item, Louies, mortes), música de cada
fase, largada dos 4 jogadores em cada fase (cada um no seu canto, com espaço
para bombar e se esconder, sem inimigo perto), 1-6 (intro, 3 duelos, torcida,
itens, vitória) e 1-7 (intro, luzes, 8 acertos, vermelho, morte, vitória), e
nas travas das intros de 1-6/1-7 todos virados para cima, sem animação de
ocioso, a pé e montados em Louie; na 1-3 cada camaleão desenhado em todo quadro
(sapo, cópia de um jogador, trocando), com os 4 montados. Na primeira execução depois de um build
ele dá boot em cada fase uma vez e guarda um savestate (`build/qa/states`); as
seguintes só rodam os cenários. Sai com código 1 se algo falhar;
`build/qa/report.txt` lista cada teste. Não faz parte do build.

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
tools/qa_check.py    testes de qualidade/regressão no Mesen (tools/qa/, tools/mesen/qa.lua)
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
