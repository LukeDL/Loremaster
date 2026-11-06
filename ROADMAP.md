
- [Loremaster — Roadmap integrado](#loremaster--roadmap-integrado)
  - [Forma de trabalho](#forma-de-trabalho)
  - [Roadmap 1 — estado consolidado](#roadmap-1--estado-consolidado)
  - [R2.1 — Base confiável e redução do débito técnico](#r21--base-confiável-e-redução-do-débito-técnico)
  - [R2.2 — Retorno à mesa](#r22--retorno-à-mesa)
  - [Débito operacional posterior](#débito-operacional-posterior)
  - [R2.3 — Mixer operacional — conclusão do M15](#r23--mixer-operacional--conclusão-do-m15)
  - [R2.4 — Integração OBS](#r24--integração-obs)
  - [R2.5 — Iluminação e automação](#r25--iluminação-e-automação)
  - [R2.6 — Sound design incremental](#r26--sound-design-incremental)
  - [R3 — Personagens da party](#r3--personagens-da-party)
    - [Incremento 1 — campanha e propriedade dos personagens](#incremento-1--campanha-e-propriedade-dos-personagens)
    - [Incremento 2 — criador guiado: atributos](#incremento-2--criador-guiado-atributos)
    - [Incremento 3 — classe, HP e reconstrução de personagem existente](#incremento-3--classe-hp-e-reconstrução-de-personagem-existente)
      - [Seleção de campanha pelo jogador](#seleção-de-campanha-pelo-jogador)
  - [Release v0.1.0 — sessão de 21/11](#release-v010--sessão-de-2111)
    - [Incremento 1 — arquitetura integrada da sessão](#incremento-1--arquitetura-integrada-da-sessão)
      - [Modelo persistente e lifecycle](#modelo-persistente-e-lifecycle)
      - [Acesso e experiência](#acesso-e-experiência)
      - [Critérios de aceite do lifecycle](#critérios-de-aceite-do-lifecycle)
    - [Incremento 2 — executor de áudio no navegador](#incremento-2--executor-de-áudio-no-navegador)
    - [Incremento 3 — gerenciamento de sessão e combate](#incremento-3--gerenciamento-de-sessão-e-combate)
      - [Contrato do primeiro MVP de combate](#contrato-do-primeiro-mvp-de-combate)
    - [Incremento 4 — conclusão mínima do personagem](#incremento-4--conclusão-mínima-do-personagem)
    - [Incremento 5 — publicação e operação](#incremento-5--publicação-e-operação)
    - [Incremento 6 — aceite da v0.1.0](#incremento-6--aceite-da-v010)
  - [Manutenção dos assets frontend](#manutenção-dos-assets-frontend)



# Loremaster — Roadmap integrado

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

**Status:** autenticação e fundação de campanhas validadas pelo mestre no
notebook real. O ciclo de campanha, identidades e versões independentes,
atributos, classe, HP e reconstrução de personagens existentes estão
implementados e aguardam validação no notebook. A linha operacional da R2.3
permanece separada.

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

### Incremento 1 — campanha e propriedade dos personagens

**Objetivo:** entregar a fundação multiusuário que permitirá construir o
criador de nível 1 sem misturar identidade, campanha, regras e ficha.

Decisões:

- o modelo suporta várias campanhas. A seleção administrativa do mestre e a
  campanha visualizada por cada jogador são independentes: cada jogador escolhe
  e persiste uma campanha entre aquelas das quais participa; quando participa
  de apenas uma, ela é selecionada automaticamente;
- a campanha possui um ciclo próprio, separado da seleção ativa da interface:
  `planning` (não iniciada), `in_progress` (em andamento) e `completed`
  (concluída). Marcar uma campanha como a selecionada no Loremaster não inicia
  sua primeira sessão;
- o mestre cria a campanha, escolhe o pacote de regras e associa jogadores pela
  interface;
- enquanto a campanha está em `planning`, o mestre define o nível inicial e as
  restrições de entrada. Ao iniciar explicitamente a primeira sessão, a campanha
  passa para `in_progress` e essas configurações mecânicas ficam bloqueadas;
- cada jogador pode manter vários personagens na mesma campanha, com no máximo
  um personagem ativo;
- personagens não são apagados durante o uso normal: podem ficar em `draft`
  (rascunho), `active` (ativo), `dead` (morto) ou `retired` (retirado);
- a identidade conceitual de um personagem é separada de sua versão em uma
  campanha. Assim, “Arthur” pode pertencer ao mesmo jogador em várias campanhas,
  mas cada participação possui progressão, estado e dados mecânicos próprios;
- ao reutilizar um personagem em outra campanha, o jogador pode começar uma nova
  versão no nível inicial definido pela campanha ou solicitar a continuidade a
  partir de um retrato da versão anterior. A versão só pode ser inscrita no nível
  inicial exato: progressões acima dele não podem ser importadas; versões abaixo
  dele percorrem sequencialmente os níveis faltantes no criador, com todas as
  escolhas feitas pelo jogador. A continuidade depende de autorização do mestre
  e cria uma cópia independente, sem sincronização posterior entre campanhas;
- o limite `N` é contado por versões de personagem dentro de cada campanha, não
  pela quantidade global de identidades conceituais do jogador;
- o jogador cria e altera somente os próprios personagens;
- o mestre visualiza todos os personagens, mas a edição mecânica pelo mestre só
  será adicionada depois, junto com um histórico auditável de alterações;
- a campanha fixa o pacote e a versão das regras. Atualizações não alteram
  silenciosamente personagens existentes;
- o primeiro pacote será identificado como D&D 5e 2024, mas conterá neste
  incremento apenas metadados e identidade de versão, sem reproduzir conteúdo
  proprietário dos livros.

Entrega vertical:

1. persistir campanhas, membros, pacotes de regras versionados, identidades de
   personagem e suas versões independentes por campanha;
2. permitir ao mestre criar uma campanha, definir a ativa e associar ou remover
   jogadores;
3. permitir ao mestre configurar o nível inicial enquanto a campanha não começou
   e iniciá-la explicitamente, bloqueando depois as restrições mecânicas de
   entrada;
4. permitir ao jogador criar, renomear, ativar e retirar seus personagens na
   campanha da qual participa, preservando também os estados morto e rascunho;
5. permitir criar uma versão de campanha a partir de uma identidade existente,
   começando no nível inicial ou copiando um retrato autorizado de outra
   campanha. Versões abaixo do nível inicial percorrem no criador cada evolução
   faltante; versões acima só podem reutilizar a identidade e recomeçar no nível
   exigido, sempre mantendo as progressões futuras independentes;
6. mostrar ao mestre a lista consolidada dos membros e personagens da campanha
   ativa;
7. aplicar propriedade e associação à campanha em todas as APIs, impedindo
   leitura ou alteração cruzada entre jogadores;
8. preservar os dados e a seleção ativa após reiniciar o Loremaster e migrar um
   banco existente com backup automático.

**Aceite:** o mestre cria “Return of the Setting Sun”, associa quatro contas de
jogador e fixa o pacote D&D 5e 2024. Cada jogador cria até N versões de
personagem por campanha e marca somente uma como ativa, sem conseguir ler ou
alterar fichas alheias. Uma mesma identidade pode originar versões independentes
em campanhas diferentes, começando novamente ou a partir de um retrato aprovado
pelo mestre, sempre no nível inicial exigido. Ao iniciar a primeira sessão, o
mestre bloqueia as restrições mecânicas de entrada da campanha. O mestre vê todos
os membros e personagens, mas não edita seus dados mecânicos. Campanha, estado do
ciclo, nível inicial, associações, personagens ativos, linhagem entre versões e
versão das regras permanecem após reiniciar a aplicação.

Ficam fora deste incremento: atributos, espécie, antecedente, classe, perícias,
equipamento, cálculos derivados, progressão de nível, conteúdo dos livros e
alterações mecânicas feitas pelo mestre.

Implementado na primeira entrega deste incremento:

- criação de campanhas pelo mestre com nome, pacote de regras e limite `N` de
  personagens por jogador;
- associação de contas ativas de jogadores durante ou após a criação;
- seleção administrativa de uma campanha ativa pelo mestre e seleção própria,
  persistente e isolada para cada jogador;
- pacote D&D 5e 2024 com metadados versionados, sem conteúdo proprietário;
- persistência no SQLite, migração com backup, autorização exclusiva do mestre
  e proteção CSRF;
- interface local acessível em `/campaigns`, ligada às telas da Engine de Som e
  de administração de jogadores.

A entrega passou pela suíte automatizada e pelo fluxo completo em navegador de
criar jogadores e criar “Return of the Setting Sun”. O mestre validou no
notebook a criação de campanhas e a associação de membros. Como correção de UX,
formulários e seletores deixam de ocupar permanentemente a página: criação e
gestão de membros usam modais, enquanto a visão principal permanece resumida em
cartões. Fluxos mais extensos devem usar páginas próprias.

A mesma organização se aplica à administração de jogadores: a página mostra
cartões resumidos; criação de conta, redefinição de senha e confirmação de
desativação usam modais, sem formulários permanentes nem prompts do navegador.

Implementado na segunda entrega deste incremento:

- ciclo `planning` → `in_progress` → `completed`, com início explícito da
  primeira sessão e bloqueio posterior do nível inicial e do limite `N`;
- identidade conceitual pertencente ao jogador e versões independentes por
  campanha, sempre criadas no nível inicial configurado;
- estados `draft`, `active`, `dead` e `retired`, com no máximo uma versão ativa
  por jogador e campanha; morte e reversão permanecem controles do mestre;
- área `/player` para criar uma identidade, reutilizá-la em outra campanha,
  renomeá-la, ativar ou retirar a versão da campanha selecionada;
- visão consolidada do mestre por campanha, preservação das versões após
  remoção e readição de membro ou desativação e reativação da conta;
- migração de bancos existentes, isolamento de propriedade, CSRF e regressões
  automatizadas para limites, estados, ciclo e acesso cruzado.

A continuidade mecânica autorizada, as escolhas guiadas para alcançar níveis
iniciais maiores e a ficha completa continuam fora desta entrega; reutilizar a
identidade não sincroniza nem simula progressão entre campanhas.

### Incremento 2 — criador guiado: atributos

**Objetivo:** estabelecer o fluxo persistente e retomável que as próximas
etapas de criação reutilizarão, começando por atributos validados no servidor.

Decisões:

- o primeiro conteúdo redistribuível usa o SRD 5.2.1, sob CC BY 4.0, como fonte
  legal do pacote público D&D 5e 2024; as Free Rules orientam a experiência,
  mas não substituem a licença de redistribuição;
- o pacote anterior, que continha somente metadados provisórios, é migrado para
  `dnd5e-2024-srd-5.2.1`, preservando as campanhas existentes;
- os métodos iniciais são array padrão `15, 14, 13, 12, 10, 8` e compra por
  pontos com orçamento 27 e valores entre 8 e 15;
- rolagem, bônus de origem e opções do PHB permanecem fora desta etapa. Conteúdo
  do PHB poderá entrar futuramente apenas como pacote privado fornecido pelo
  mestre, sem publicação no repositório;
- atributos pertencem à versão do personagem na campanha, não à identidade
  global, e não são copiados ao reutilizar a identidade em outra campanha;
- o jogador pode salvar uma distribuição parcial, sair e retomar. Concluir a
  etapa exige seis valores válidos e ativar o personagem exige atributos
  concluídos;
- alterações posteriores em um rascunho reabrem a etapa. Personagens ativos,
  mortos ou retirados não podem editar os atributos por esse fluxo;
- o mestre acompanha `não iniciado`, `em andamento` ou `concluído`, mas não
  preenche escolhas pelo jogador.
- o fluxo completo seguirá a ordem recomendada nas regras de 2024: classe,
  origem (antecedente, espécie e idiomas), atributos, alinhamento e detalhes;
- a etapa final de detalhes incluirá a imagem do personagem, enviada pelo
  jogador e vinculada somente à versão daquela campanha;
- trocar entre array padrão e compra por pontos preserva os valores locais. A
  compra por pontos usa controles diretos de menos/valor/mais; o array padrão
  mantém seletores para deixar explícitos os valores ainda disponíveis.

Implementado:

- migração `009_add_srd_ability_scores`, com backup automático já oferecido
  pelo mecanismo de migrações e sem inventar atributos para versões existentes;
- tabela por versão de campanha, proveniência pelo pacote fixado na campanha e
  atribuição do SRD em `THIRD_PARTY_NOTICES.md` e na página do criador;
- APIs isoladas por propriedade, campanha selecionada e associação atual para
  carregar, substituir e concluir a distribuição;
- validação no servidor do multiconjunto do array padrão, tabela de custo da
  compra por pontos, orçamento, faixas e preenchimento completo;
- página própria em `/player/characters/{version_id}/creator`, com método,
  distribuição, modificadores, orçamento, salvamento e retomada;
- progresso nos cartões do jogador e no roster do mestre, sem controles de
  edição mecânica para o mestre;
- regressões de domínio, persistência, ativação, isolamento, remoção e readição
  de membro, independência entre campanhas, CSRF, migração e contrato da página.

**Aceite:** o jogador cria um rascunho, distribui parcialmente os atributos por
um dos dois métodos, sai e retoma sem perda. O servidor rejeita valores,
duplicações ou custos inválidos, outro jogador não acessa o rascunho e o mestre
vê apenas o progresso. Após concluir seis atributos válidos, o jogador pode
ativar a versão; uma identidade reutilizada em outra campanha começa sem dados
mecânicos copiados.

### Incremento 3 — classe, HP e reconstrução de personagem existente

**Objetivo:** atender tanto personagens novos quanto campanhas já em andamento,
sem rerrolar ou inventar o histórico mecânico de uma ficha existente.

Decisões:

- cada versão registra `new_character` ou `manual_import`; reutilizar uma
  identidade não permite inferir o modo de entrada;
- personagem novo escolhe uma classe do SRD 5.2.1. O HP de nível 1 usa o máximo
  do Dado de Vida mais Constituição; quando a campanha começa acima do nível 1,
  os níveis posteriores usam a progressão fixa do pacote;
- reconstruções só podem nascer em campanhas `in_progress`, aceitam composição
  multiclasse cuja soma corresponde ao nível total e preservam atributos e HP
  atuais como baseline manual;
- `current_hp = 0` é um estado válido. O sistema separa HP máximo, atual e
  temporário e registra o modificador de Constituição do baseline;
- o snapshot reconstruído passa por `draft` → `pending` → `approved` ou
  `changes_requested`. Enquanto aguarda revisão, o jogador não altera os dados;
  aprovação e devolução correspondem à revisão submetida;
- o Mestre confere e aprova ou devolve com observação, mas não substitui as
  escolhas do jogador;
- níveis futuros poderão usar valor fixo, resultado de dado físico ou roller
  autoritativo do servidor. O histórico anterior não será decomposto em
  resultados fictícios.

Implementado:

- migração `010_add_character_classes_imports_and_hp`, preservando versões
  existentes como `new_character` sem inventar classe ou HP;
- catálogo público das 12 classes do SRD 5.2.1, composição multiclasse importada,
  classe inicial e validação da soma de níveis;
- cálculo autoritativo de HP para personagem novo e baseline manual auditável
  para reconstruções;
- APIs de jogador isoladas por propriedade, campanha selecionada e associação,
  além de revisão exclusiva do Mestre;
- escolha do modo de entrada no modal de personagem, criador dedicado para
  classe, atributos e HP, e revisão da importação em modal no roster do Mestre;
- regressões para regras de HP, multiclasse, `current_hp = 0`, bloqueio durante
  revisão, correção e nova submissão, ativação após aprovação e migração.

#### Seleção de campanha pelo jogador

A campanha selecionada pelo Mestre é somente o contexto administrativo dele e
não restringe mais os personagens que cada jogador pode consultar ou alterar.
Cada jogador mantém sua própria campanha selecionada, persistida na conta e
validada contra as associações atuais.

- com nenhuma campanha associada, não há contexto de personagem disponível;
- com uma única campanha, ela é selecionada automaticamente e o seletor fica
  oculto;
- com duas ou mais campanhas, a página **Meus personagens** exibe um seletor
  próprio, persistente e independente da seleção do Mestre;
- remover o jogador de uma campanha limpa a seleção persistida, impedindo que
  uma escolha antiga reapareça silenciosamente se a associação for recriada;
- uma seleção rejeitada pelo servidor faz a interface recarregar o estado
  autoritativo, sem manter uma opção inválida visível;
- o seletor e os controles da reconstrução seguem o tema do Loremaster e foram
  ajustados para telas estreitas sem criar overflow horizontal.

O comportamento possui regressões de isolamento entre jogadores e campanhas,
validação de associação, limpeza da seleção e contrato da interface. O smoke
visual confirmou o seletor oculto com uma única campanha e a navegação entre
duas campanhas em viewport móvel.

Validação real concluída no notebook: o Mestre manteve uma campanha em seu
contexto administrativo enquanto o jogador selecionou e consultou outra
campanha de forma independente. O comportamento foi confirmado como funcional.

**Aceite:** em uma campanha em andamento, o jogador reconstrói um personagem de
nível 7 como Guerreiro 5/Mago 2, transcreve atributos e HP sem rerrolar, envia um
snapshot e fica impedido de alterá-lo até o Mestre aprovar ou devolver. Após a
aprovação, pode ativar a versão. Em uma campanha nova, classe e Constituição
produzem o HP correto sem o cliente informar um total arbitrário.

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

## Release v0.1.0 — sessão de 21/11

Esta release reúne a Engine de Som, campanhas, personagens e o futuro controle
de sessão em uma única aplicação e uma única fonte de dados. A superfície
externa inicial fica restrita a campanhas e personagens, sem remover as
capacidades privadas do Mestre. A linha de integração é `main`; cada incremento
é desenvolvido em uma branch curta e só entra em `main` após verificação e
aceite.

### Incremento 1 — arquitetura integrada da sessão

Este incremento entrega um corte vertical utilizável do lifecycle de sessões,
não apenas documentação. Campanha, sessão de jogo e encontro são conceitos
independentes:

```text
Campanha
  └── Sessões de jogo
        └── Encontros de combate
              └── Rodadas e turnos
```

Selecionar uma campanha não inicia campanha nem sessão. Iniciar uma sessão não
conclui o planejamento da campanha: o Mestre deve primeiro executar a ação
separada de iniciar a campanha, que muda `planning` para `in_progress` e trava
nível inicial e limite de personagens.

#### Modelo persistente e lifecycle

- usar `game_sessions`, pois `sessions` já armazena sessões de autenticação;
- identificar cada sessão por número e título opcional;
- exigir que o primeiro número seja informado pelo Mestre, permitindo migrar
  campanhas que já estejam, por exemplo, na sessão 6;
- sugerir o maior número existente mais um nas sessões seguintes, mantendo o
  campo editável, permitindo lacunas e rejeitando duplicatas na campanha;
- aceitar sessão 0 para campanhas que usem uma sessão zero;
- criar a sessão diretamente em `live`, sem um estado intermediário `draft`;
- suportar `live`, `paused` e `completed`, sem reabrir uma sessão encerrada;
- permitir pausar, retomar ou encerrar uma sessão ao vivo, e retomar ou encerrar
  uma sessão pausada;
- permitir no máximo uma sessão `live` ou `paused` por campanha, protegida
  também por índice parcial no SQLite;
- bloquear novas sessões em campanhas `planning` ou `completed`;
- manter a campanha `in_progress` ao encerrar uma sessão;
- persistir uma `revision` e exigir `expected_revision` nas mutações para
  rejeitar comandos concorrentes ou baseados em estado obsoleto;
- manter um log append-only em `game_session_events` com tipo, revisão, ator,
  payload e horário para `session_started`, `session_paused`, `session_resumed`
  e `session_completed`.

O estado materializado em `game_sessions` é a fonte autoritativa após reinício,
pausa ou reconexão. O log existe para auditoria e para sustentar os comandos de
combate posteriores, sem exigir reconstruir o estado corrente a cada leitura.

#### Acesso e experiência

- somente `gm` pode iniciar, pausar, retomar ou encerrar uma sessão;
- jogadores recebem visão somente leitura da sessão da campanha que eles
  próprios selecionaram, sempre validada contra a membership atual;
- a campanha administrativamente selecionada pelo Mestre não restringe o
  contexto visualizado por jogadores;
- a página de campanhas permanece `summary-first`, mostrando sessão atual ou
  última sessão e abrindo um modal delimitado para número e título;
- o controle prolongado usa uma página própria de sessão, inicialmente com
  campanha, número, título, estado, horários, ações e histórico básico;
- a visão do jogador acompanha as transições em tempo real sem oferecer ações;
- não abrir o WebSocket de áudio `/ws` para jogadores; criar um canal de sessão
  autenticado, filtrado por campanha e com payloads adequados ao papel;
- manter mutações em APIs REST protegidas por autenticação e CSRF; o WebSocket
  é servidor → cliente e entrega snapshot autoritativo após reconexão;
- renomear internamente a rota atualmente chamada `start_first_session`, pois
  ela inicia a campanha, não uma sessão de jogo, preservando a URL somente se
  necessário para compatibilidade.

#### Critérios de aceite do lifecycle

1. O Mestre inicia a campanha separadamente e cria manualmente a sessão 6.
2. A criação seguinte sugere 7, mas aceita edição e rejeita número duplicado.
3. Não é possível abrir outra sessão enquanto a atual estiver ao vivo ou
   pausada, inclusive sob requisições concorrentes.
4. Pausar, recarregar e reiniciar o Loremaster preserva o estado pausado.
5. O Mestre retoma e encerra; a campanha continua `in_progress`.
6. A sessão encerrada permanece no histórico e não pode ser reaberta.
7. Jogador associado acompanha transições em tempo real sem poder alterá-las.
8. Jogador não associado não lê a sessão nem recebe eventos dela.
9. Duas abas do Mestre não aplicam comandos a partir da mesma revisão.
10. A migração preserva bancos existentes e a suíte cobre lifecycle,
    autorização, membership, concorrência, persistência e WebSocket.
11. O fluxo completo é exercitado em navegador real antes da publicação.

### Incremento 2 — executor de áudio no navegador

- criar uma prova técnica com Web Audio no navegador do Mestre;
- exigir ativação explícita e indicar claramente o estado do áudio;
- suportar camadas, volume, pan, intro → loop → tail, fades e crossfades;
- pré-carregar assets necessários e recuperar contextos suspensos;
- eleger um único cliente como executor de áudio ativo;
- manter a engine Python como fallback até a validação em sessão real.

### Incremento 3 — gerenciamento de sessão e combate

O combate usa as sessões persistentes do Incremento 1. O servidor mantém estado
autoritativo para reconexão e auditoria, integra personagens ativos da campanha
e mantém todas as decisões sob controle do Mestre.

#### Contrato do primeiro MVP de combate

- permitir um encontro ativo por sessão, preservando o histórico dos encontros
  finalizados e cancelados;
- permitir cancelar sem aplicar alterações às fichas, preservando o encontro
  no histórico com estado `cancelled`;
- representar inimigos, aliados e NPCs como participantes manuais do encontro,
  sem exigir fichas persistentes completas;
- controlar iniciativa, ordem, rodadas e turnos;
- controlar HP, HP temporário, dano, cura, condições e testes de morte;
- manter alterações de HP dos personagens no encontro até o Mestre revisar e
  finalizar; a aplicação às fichas ocorre em uma única transação;
- alertar quando uma condição vencer, sem removê-la automaticamente;
- ao encerrar o encontro, pedir confirmação individual das condições que
  continuam no estado da sessão;
- ao atingir três falhas em testes de morte, alertar e exigir confirmação do
  Mestre antes de marcar a versão do personagem como `dead`;
- permitir somente ao Mestre alterar o estado do combate na primeira versão;
- permitir que jogadores acompanhem ordem, turno e condições em tempo real,
  mantendo oculto o HP exato de inimigos.

### Incremento 4 — conclusão mínima do personagem

- completar Origem, Atributos, Alinhamento e Detalhes na ordem definida;
- manter todas as escolhas persistentes, retomáveis e validadas no servidor;
- registrar procedência e versão do pacote de regras;
- permitir retrato na etapa final sem acoplar identidades entre campanhas;
- entregar uma ficha mínima utilizável durante a sessão.

### Incremento 5 — publicação e operação

- empacotar a aplicação para uma VM Ubuntu com Docker Compose;
- manter SQLite persistente enquanto houver uma única instância de baixa
  concorrência;
- publicar por Cloudflare Tunnel sem expor diretamente o IP residencial;
- aplicar autenticação, autorização, cookies seguros, limites de login e
  tratamento confiável de proxy;
- publicar imagens imutáveis no GHCR e uma GitHub Release versionada;
- fornecer `upgrade.sh` com preflight, backup, migração, health check e rollback.

### Incremento 6 — aceite da v0.1.0

- executar uma sessão simulada completa antes de 21/11;
- validar áudio no notebook do Mestre e a contingência pela engine Python;
- validar acesso remoto de jogadores, isolamento e reconexão;
- percorrer o fluxo de combate definido sem perda de estado;
- comprovar backup, restauração, upgrade e rollback;
- publicar a beta privada somente após todos os gates obrigatórios passarem.

## Manutenção dos assets frontend

O app não usa CDN. Vue, Vue Flow e wavesurfer ficam em
`src/loremaster/web/vendor/`. Uma atualização deve substituir os arquivos pelas
distribuições oficiais, abrir `/` e `/map` e confirmar no DevTools que nenhuma
requisição sai para domínio externo. Os smoke tests headless verificam que os
assets referenciados continuam locais e disponíveis.