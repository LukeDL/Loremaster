# Loremaster — Roadmap 2

O Loremaster é uma ferramenta local-first para áudio, luz e ambientação em
sessões de RPG. A aplicação deve continuar utilizável sem internet, com o
notebook como servidor e o tablet como controle.

## Forma de trabalho

- Uma entrega ativa por vez e uma única linha de integração.
- Cada entrega termina em capacidade utilizável e verificada.
- Testes automatizados não usam o banco nem os áudios reais.
- Decisões duráveis ficam neste arquivo; problemas locais ficam em
  `ISSUES.md`, que não é versionado.
- Funcionalidades novas só avançam após a base anterior estar verde.

## Roadmap 1 — estado consolidado

Entregue até o M14:

- aplicação local com FastAPI, SQLite e engine de áudio em camadas;
- upload, cenas, volume por camada e controle pelo tablet;
- grafo visual de cenas em `/map`, com entrada, transições e posições;
- operação offline, com dependências frontend vendorizadas;
- regiões intro → loop → tail e editor visual dos marcadores;
- painel de reprodução e waveforms;
- pan estéreo equal-power na engine;
- jump-to-tail com crossfade sem bloquear novos comandos.

Pendências herdadas:

- mixer completo na interface, antigo M15;
- integrações OBS, Home Assistant e MQTT;
- buses, efeitos e sound design avançado;
- validação em sessões reais e empacotamento operacional.

Iniciativa, dice roller e timer permanecem estacionados: não são parte do foco
de áudio, luz e ambientação. Multiusuário passa a ter um destino restrito no
módulo de personagens descrito em R3, sem entrar na linha ativa antes da
validação da R2.3.

## R2.1 — Base confiável e redução do débito técnico

**Status:** concluído e validado no notebook real.

Entregue:

- imports lazy e lifespan injetável para testes sem PortAudio;
- suíte headless alinhada ao pan equal-power do M13;
- migrações SQLite ordenadas e registradas em `schema_migrations`;
- backup automático antes de migrar bancos legados;
- migração de `loop_start_ms`, `loop_end_ms`, `is_entry` e `pan_lr`;
- `PRAGMA foreign_keys=ON` em todas as conexões e verificação de órfãos;
- rejeição de cenas com áudios ou destinos `goto` inexistentes;
- bloqueio da exclusão de uma cena ainda usada por uma transição;
- validação, no startup, dos arquivos físicos usados pelas cenas;
- diretório de dados apropriado à plataforma, com override por
  `LOREMASTER_DATA_DIR` e compatibilidade com checkout legado;
- regressões de hidratação, pan e jump-to-tail;
- correção para que `on_end.stop` preserve a tail; o botão Stop continua
  interrompendo todas as camadas imediatamente;
- smoke tests de `/`, `/map` e todos os assets locais.

Aceite automatizado:

- suíte completa passa sem dispositivo de áudio;
- uma cópia de banco legado é migrada sem perda e com backup verificável;
- build de sdist/wheel e `git diff --check` passam.

Gate concluído pela R2.2 com cópia dos dados reais e dispositivo de áudio do
notebook.

## R2.2 — Retorno à mesa

**Status:** concluído.

Objetivo: executar a aplicação diretamente do checkout no notebook e validar
o comportamento em hardware real, sem antecipar infraestrutura de release.

1. preservar a R2.1 em commit local;
2. atualizar ou copiar o checkout para o notebook;
3. copiar `data/` para backup e testar somente sobre uma segunda cópia;
4. executar `uv sync --dev` e `uv run loremaster`;
5. validar banco migrado, arquivos de áudio e abertura das cenas;
6. exercitar volume, pan, intro/loop/tail, `goto`, `return_previous`,
   `on_end.stop` e o botão Stop no dispositivo de áudio real;
7. controlar a execução pelo tablet e repetir o fluxo sem internet;
8. registrar e corrigir somente os problemas observados nesse uso.

Ficam fora desta entrega: instalador, launcher, `doctor`, PyInstaller, release
candidate, rotação de logs e rollback automatizado.

**Aceite:** uma cena real é preparada e executada pelo checkout Dev no
notebook, incluindo transição e tail, com controle pelo tablet.

Validação concluída no notebook de desenvolvimento com banco e áudios reais,
incluindo mixer, transições, tail, controle pelo tablet e operação offline.

## Débito operacional posterior

Limite de upload, decodificação fora do event loop, cache LRU, estados de erro
da interface e responsividade do mapa permanecem registrados, mas só entram
na linha ativa quando o teste real demonstrar sua prioridade.

## R2.3 — Mixer operacional — conclusão do M15

**Status:** implementado localmente; aguardando validação no notebook.

Entregue:

- faders de volume e pan na interface;
- controles consistentes em `/` e no painel do `/map`;
- feedback de falha em play, stop e alterações de parâmetros;
- grupos simples de música, ambiente e SFX;
- volume por grupo persistido na cena;
- nomes acessíveis e operação por teclado nos controles críticos;
- migração de bancos existentes com todas as camadas no grupo `ambience` e
  volumes de grupo em 100%.

**Aceite:** executar uma cena com camadas nos três grupos, ajustar volume e pan
em `/` e `/map`, recarregar a aplicação e confirmar a persistência dos volumes
de grupo sem regressão nas transições e tails.

## R2.4 — Integração OBS

- conexão configurável via OBS WebSocket;
- associação entre cena do Loremaster e cena do OBS;
- troca automática em `ScenePlaybackStarted`;
- falha do OBS não interrompe o áudio;
- suporte posterior a overlays de mapas e imagens.

## R2.5 — Iluminação e automação

Entregas separadas, nesta ordem:

1. Home Assistant para cenas de iluminação;
2. presets de ambiente vinculados às cenas;
3. MQTT apenas se um dispositivo ou fluxo real exigir a ponte.

## R2.6 — Sound design incremental

1. buses;
2. filtros e EQ simples;
3. ducking/sidechain;
4. reverb e delay;
5. somente depois avaliar um editor completo em DAG.

Cenas simples permanecem compatíveis. O grafo avançado não será construído
antes de algumas sessões reais indicarem quais roteamentos são úteis.

## R3 — Personagens da party

**Status:** autenticação do primeiro MVP implementada e validada pelo mestre no
notebook real. A linha operacional da R2.3 permanece separada.

Objetivo: permitir que cada jogador crie, evolua e use seu personagem no
Loremaster, com progressão completa do nível 1 ao 20 segundo D&D 5e 2024. O
suporte a D&D 5e 2014 será acrescentado depois sem misturar regras das duas
edições.

Decisões de produto:

- acesso inicial pela rede local, no navegador de cada jogador;
- autenticação por usuário e senha desde o primeiro MVP, com dois papéis
  explícitos: `player` e `gm`;
- cada `player` acessa e altera somente os próprios personagens;
- o `gm` administra os jogadores, visualiza todos os personagens e tem acesso
  exclusivo ao mixer, mapa, cenas, uploads, playback e demais funções da engine
  de som;
- o mestre cria, desativa e redefine as credenciais dos jogadores; não existe
  cadastro público no primeiro MVP;
- senhas nunca são armazenadas em texto puro; sessões autenticadas usam cookies
  `HttpOnly` e `SameSite`, acrescentando `Secure` sob HTTPS, e as APIs e o
  WebSocket aplicam autorização no servidor, sem confiar apenas em menus
  ocultos na interface;
- a conta inicial do mestre é criada por um fluxo local de bootstrap, sem senha
  padrão no código ou no repositório;
- arquitetura preparada para acesso remoto posterior, mas a instalação não será
  exposta à internet antes de HTTPS, proteção contra tentativas repetidas e
  recuperação segura de conta;
- criação guiada, ficha digital jogável e progressão até o nível 20;
- regras, conteúdo e dados do personagem separados: cada campanha fixa a
  edição e os pacotes de conteúdo permitidos;
- suporte explícito a conteúdo oficial autorizado e homebrew, com indicação da
  origem de cada opção;
- nenhum texto proprietário de livro será distribuído com o aplicativo sem
  licença; o núcleo pode incluir apenas conteúdo cuja licença permita a
  redistribuição e aceitar pacotes privados fornecidos pelo mestre;
- escolhas inválidas devem ser explicadas e bloqueadas no fluxo guiado, sem
  impedir que o mestre aplique uma exceção auditável à campanha.

A entrega completa será construída em incrementos verticais utilizáveis:

1. autenticação por usuário e senha, papéis `player`/`gm`, bootstrap local do
   mestre, administração de jogadores e proteção da engine de som;
2. fundação de campanhas, propriedade dos personagens e pacotes de regras
   versionados;
3. criação de nível 1 com atributos, espécie, antecedente, classe, perícias,
   equipamento e cálculos derivados;
4. ficha jogável com recursos, descanso, pontos de vida, condições, ataques,
   magias e inventário;
5. progressão validada do nível 2 ao 20, incluindo multiclasse, talentos,
   subclasses e preparação de magias;
6. importação privada de conteúdo autorizado, homebrew e ferramentas de
   revisão do mestre;
7. suporte à edição 2014 por pacotes de regras e migração ou duplicação
   explícita do personagem, sem conversão silenciosa.

Entregue no incremento de autenticação:

- bootstrap local da primeira conta `gm`, sem senha padrão;
- login e logout com sessão opaca persistida no SQLite;
- senhas protegidas por Argon2id e tokens de sessão armazenados apenas como
  hash;
- administração de contas `player` pelo mestre, incluindo desativação e
  redefinição de senha;
- proteção no servidor das páginas, APIs e WebSocket da Engine de Som;
- isolamento do jogador em uma área própria, ainda sem o criador de
  personagens;
- proteção CSRF nas operações mutáveis e migração com backup dos bancos
  existentes.

Validação real concluída no notebook após `git pull`, sincronização das
dependências, bootstrap da conta `gm` e execução do fluxo autenticado. O
resultado foi confirmado pelo mestre como funcional.

### Próximo incremento — campanha e propriedade dos personagens

**Objetivo:** entregar a fundação multiusuário que permitirá construir o
criador de nível 1 sem misturar identidade, campanha, regras e ficha.

Decisões:

- o modelo suporta várias campanhas, mas a interface opera sobre uma única
  campanha ativa por vez;
- o mestre cria a campanha, escolhe o pacote de regras e associa jogadores pela
  interface;
- cada jogador pode manter vários personagens na mesma campanha, com no máximo
  um personagem ativo;
- personagens não são apagados durante o uso normal: podem ficar em rascunho,
  ativos ou retirados;
- o jogador cria e altera somente os próprios personagens;
- o mestre visualiza todos os personagens, mas a edição mecânica pelo mestre só
  será adicionada depois, junto com um histórico auditável de alterações;
- a campanha fixa o pacote e a versão das regras. Atualizações não alteram
  silenciosamente personagens existentes;
- o primeiro pacote será identificado como D&D 5e 2024, mas conterá neste
  incremento apenas metadados e identidade de versão, sem reproduzir conteúdo
  proprietário dos livros.

Entrega vertical:

1. persistir campanhas, membros, pacotes de regras versionados e personagens;
2. permitir ao mestre criar uma campanha, definir a ativa e associar ou remover
   jogadores;
3. permitir ao jogador criar, renomear, ativar e retirar seus personagens na
   campanha da qual participa;
4. mostrar ao mestre a lista consolidada dos membros e personagens da campanha
   ativa;
5. aplicar propriedade e associação à campanha em todas as APIs, impedindo
   leitura ou alteração cruzada entre jogadores;
6. preservar os dados e a seleção ativa após reiniciar o Loremaster e migrar um
   banco existente com backup automático.

**Aceite:** o mestre cria “Return of the Setting Sun”, associa quatro contas de
jogador e fixa o pacote D&D 5e 2024. Cada jogador cria até N personagens e marca
somente um como ativo, sem conseguir ler ou alterar fichas alheias. O mestre vê
todos os membros e personagens, mas não edita seus dados mecânicos. Campanha,
associações, personagens ativos e versão das regras permanecem após reiniciar a
aplicação.

Ficam fora deste incremento: atributos, espécie, antecedente, classe, perícias,
equipamento, cálculos derivados, progressão de nível, conteúdo dos livros e
alterações mecânicas feitas pelo mestre.

**Aceite do primeiro MVP:** o mestre executa o bootstrap local, entra com usuário
e senha, cria quatro contas de jogador, visualiza todas as fichas e opera a
engine de som. Cada jogador entra separadamente, não consegue acessar a engine
nem ler ou alterar o personagem dos demais e mantém sua sessão e seus dados
após reiniciar o Loremaster.

**Aceite do módulo completo:** os quatro jogadores criam personagens legais de
D&D 5e 2024, evoluem-nos até o nível 20 por caminhos de classe única e
multiclasse e usam as fichas durante a sessão. A suíte cobre autenticação,
autorização, isolamento entre jogadores, cálculos, pré-requisitos e progressão
sem depender do banco nem dos dados reais.

## Manutenção dos assets frontend

O app não usa CDN. Vue, Vue Flow e wavesurfer ficam em
`src/loremaster/web/vendor/`. Uma atualização deve substituir os arquivos pelas
distribuições oficiais, abrir `/` e `/map` e confirmar no DevTools que nenhuma
requisição sai para domínio externo. Os smoke tests headless verificam que os
assets referenciados continuam locais e disponíveis.