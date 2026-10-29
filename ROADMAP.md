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

Multiusuário, iniciativa, dice roller e timer permanecem estacionados: não são
parte do foco de áudio, luz e ambientação.

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

## Manutenção dos assets frontend

O app não usa CDN. Vue, Vue Flow e wavesurfer ficam em
`src/loremaster/web/vendor/`. Uma atualização deve substituir os arquivos pelas
distribuições oficiais, abrir `/` e `/map` e confirmar no DevTools que nenhuma
requisição sai para domínio externo. Os smoke tests headless verificam que os
assets referenciados continuam locais e disponíveis.