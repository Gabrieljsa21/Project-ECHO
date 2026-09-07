# Plano de implementação - ECHO Player leve

## Objetivo

Transformar o Project ECHO em um player musical próprio, preservando a inteligência existente e mantendo baixo consumo de CPU, memória, processos, GPU, disco e rede.

## Princípios obrigatórios

- O ECHO é a única autoridade sobre fila, faixa atual e histórico.
- Desktop, GAIA e ERIS são apenas clientes e controles.
- O Desktop pode ser encerrado sem interromper a reprodução.
- Somente o processo Python do ECHO permanece ativo em repouso.
- O mecanismo de áudio funciona sob demanda.
- Não usar Electron.
- Não criar marketplace ou execução dinâmica de plugins no MVP.
- Não usar polling rápido, visualizadores, waveforms ou efeitos permanentes.
- Cada fase deve ser entregue em uma Pull Request separada.
- Não copiar implementações GPL ou AGPL dos projetos estudados.

## Arquitetura pretendida

```text
                 ECHO - processo principal
 ┌─────────────────────────────────────────────────┐
 │ Inteligência musical                            │
 │ Catálogo e biblioteca                           │
 │ Fila e estado autoritativo                      │
 │ Source Resolver                                 │
 │ Histórico / SQLite                              │
 │ API local + eventos                             │
 └──────────────────────┬──────────────────────────┘
                        │
               Playback Adapter
                        │
                      MPV
                        │
                     Áudio

      Desktop Tauri ─┐
               GAIA ─┼── API local do ECHO
       ERIS/Discord ─┘
```

O Player Core será um módulo lógico dentro do processo atual do ECHO, não um serviço independente. O MPV apenas decodifica e reproduz o áudio; ele não decide a próxima música nem mantém o estado oficial da fila.

## Fase 0 - Baseline e protótipo de desempenho

Antes de alterar a arquitetura:

1. Medir o ECHO atual:
   - RAM privada e working set.
   - CPU ociosa.
   - Quantidade de processos, threads e handles.
   - Tempo de inicialização.
   - Atividade de disco e rede em repouso.

2. Criar um protótipo descartável contendo:
   - ECHO Python.
   - MPV controlado por IPC.
   - Uma janela Tauri mínima.
   - Play, pause e posição.

3. Medir cinco cenários:
   - ECHO ocioso.
   - Tocando sem Desktop.
   - Tocando com Desktop aberto.
   - Desktop minimizado.
   - Desktop realmente encerrado.

4. Confirmar que fechar o Desktop remove todos os processos WebView2 relacionados a ele.

### Metas iniciais

As metas devem ser revistas após a primeira medição no hardware real.

| Cenário | RAM total | CPU média |
|---|---:|---:|
| ECHO ocioso | até 50 MB | abaixo de 0,2% |
| Reprodução sem interface | até 120 MB | abaixo de 3% |
| Reprodução com interface | até 220 MB | abaixo de 4% |
| Interface aberta sem interação | estável | abaixo de 1% |

Condições adicionais:

- Crescimento de memória inferior a 10% após duas horas.
- Nenhuma consulta periódica desnecessária a providers.
- Nenhum processo do Desktop depois que ele for encerrado.
- Nenhuma atividade de CPU ociosa sem causa identificada.

Se o protótipo Tauri ultrapassar muito esses limites, avaliar uma interface nativa Windows antes de construir a interface completa.

## Fase 1 - Preparar o domínio musical

Criar modelos independentes dos providers:

```text
Track
- id interno
- título
- artistas
- álbum
- duração
- external_ids
- metadata

QueueEntry
- id próprio
- track_id
- origem
- adicionado_por
- posição

SourceCandidate
- provider
- source_id
- confiança
- duração encontrada

ResolvedSource
- URI
- headers
- formato
- qualidade
- expires_at
```

Trabalhos:

- Parar de usar `artista::título` como identidade definitiva.
- Manter compatibilidade com o histórico antigo durante a migração.
- Criar um usuário interno do ECHO.
- Mapear `discord_user_id` para esse usuário, em vez de tratá-lo como identidade central.
- Separar quem controla a sessão de quem receberá os efeitos de preferência.

### Gate da fase

- Todos os testes atuais continuam passando.
- Caos, pools, votos e descoberta continuam funcionando sem conhecer fontes de reprodução.

## Fase 2 - SQLite e migração dos JSONs

Substituir gradualmente os arquivos JSON regravados integralmente.

Tabelas mínimas:

- `users`
- `user_identities`
- `tracks`
- `track_external_ids`
- `recommendations`
- `listening_events`
- `ratings`
- `playback_state`
- `queue_entries`
- `source_cache`

Regras:

- SQLite em modo WAL.
- Migração automática e idempotente dos JSONs.
- Backup dos JSONs antes da primeira migração.
- Nunca gravar posição a cada atualização da barra.
- Persistir posição em checkpoints espaçados, pause, skip e encerramento.
- URLs temporárias de reprodução não devem permanecer armazenadas indefinidamente.

### Gate da fase

- Executar a migração duas vezes não duplica dados.
- O histórico permanece equivalente.
- Uma interrupção durante uma gravação não corrompe fila ou histórico.

## Fase 3 - Player Core headless

Implementar dentro do processo Python do ECHO:

- Máquina de estados:
  - `stopped`
  - `resolving`
  - `buffering`
  - `playing`
  - `paused`
  - `error`
- Fila autoritativa.
- Faixa atual.
- Play, pause, resume e stop.
- Próxima e anterior.
- Seek e volume.
- Repeat off/all/one.
- Shuffle determinístico e restaurável.
- Tocar agora, tocar depois e adicionar ao final.
- Restauração da fila após reiniciar o ECHO.

Cada ocorrência da mesma música deve possuir um `QueueEntry.id` diferente.

### Gate da fase

- Dois clientes executando comandos simultâneos não criam estados divergentes.
- Reiniciar o ECHO restaura fila e posição, mas não começa a tocar sozinho.
- Todo skip passa pela mesma função, independentemente da origem.

## Fase 4 - MPV como mecanismo de áudio

Criar uma interface pequena:

```text
PlaybackAdapter
- load
- play
- pause
- stop
- seek
- set_volume
- get_status
- shutdown
```

A primeira implementação será `MpvAdapter`.

Comportamento:

- Iniciar MPV somente quando necessário.
- Controlar por IPC local.
- Encerrar após período configurável sem reprodução.
- Limitar o buffer de memória.
- Desabilitar vídeo.
- Enviar apenas a faixa atual e, quando útil, a próxima.
- Reiniciar o MPV automaticamente se ele falhar.
- Uma falha no MPV não pode derrubar o ECHO.
- Pré-carregar ou resolver a próxima faixa perto do final da atual.

### Gate da fase

- Reprodução contínua por duas horas sem crescimento progressivo de memória.
- Skip repetido não deixa processos MPV órfãos.
- Pausar por longo período não mantém atividade relevante de CPU.

## Fase 5 - Source Resolver

Dividir o provider atual em capacidades:

- `MetadataProvider`
- `SearchProvider`
- `RecommendationProvider`
- `StreamProvider`
- `LyricsProvider`
- `ArtworkProvider`

Não implementar plugins dinâmicos. Usar providers registrados no código.

Fluxo:

```text
Track escolhido pelo ECHO
       ↓
buscar candidatos
       ↓
comparar título, artista e duração
       ↓
resolver stream do melhor candidato
       ↓
testar fonte
       ↓
enviar ao MPV
```

Recursos obrigatórios:

- Cancelar uma resolução se outro comando substituí-la.
- Timeout por provider.
- Fallback entre candidatos e providers.
- URLs com expiração.
- Suporte a headers, cookies e user-agent quando necessário.
- Cache limitado por tamanho e tempo.
- Não alterar o objeto `Track` com informações temporárias da fonte.

### Gate da fase

- Provider indisponível não bloqueia permanentemente a fila.
- Uma URL expirada é renovada e a reprodução continua na mesma posição.
- O algoritmo de recomendação não sabe qual provider forneceu o áudio.

## Fase 6 - API local única

Evoluir a API existente sem transformá-la em um serviço de rede público.

Endpoints essenciais:

```text
GET  /v1/player
POST /v1/player/play
POST /v1/player/pause
POST /v1/player/skip
POST /v1/player/previous
POST /v1/player/seek
POST /v1/player/volume

GET    /v1/queue
POST   /v1/queue
DELETE /v1/queue/{entry_id}

POST /v1/feedback
POST /v1/discovery/start
GET  /v1/events
```

Regras:

- Escutar apenas em `127.0.0.1`.
- Token local obrigatório.
- API versionada.
- Comandos aceitam um `action_id` para evitar duplicações.
- O estado possui um número de revisão crescente.
- Usar SSE para mudanças de estado e fila.
- A interface calcula o progresso entre eventos.
- Não enviar dezenas de eventos de posição por segundo.

### Gate da fase

- Desktop, ERIS e GAIA veem o mesmo estado.
- Repetir acidentalmente o mesmo comando não executa dois skips.
- Um cliente lento não bloqueia os demais.

## Fase 7 - ECHO Desktop mínimo

Stack proposta:

- Tauri 2.
- Svelte ou frontend equivalente pequeno.
- Sem estado musical autoritativo no frontend.
- Sem processo auxiliar próprio além do ECHO.
- Listas virtualizadas.
- Capas carregadas e redimensionadas sob demanda.

Primeiras telas:

1. Tocando agora.
2. Fila.
3. Busca.
4. Gostei.
5. Histórico.
6. Caos e descoberta.
7. Letras simples.
8. Configurações básicas.

Evitar no MVP:

- Visualizador.
- Waveform.
- Vídeo.
- Equalizador gráfico.
- Fundos animados.
- Extração contínua de cores.
- Transições com blur em grandes áreas.
- Múltiplos temas.
- Editor avançado de playlists.

### Gate da fase

- Fechar a janela encerra o Desktop de verdade.
- O ECHO e a reprodução continuam.
- Abrir novamente reconstrói a interface a partir do estado do ECHO.
- Scroll de listas grandes não causa aumento contínuo de RAM.

## Fase 8 - Migrar ERIS e GAIA

- ERIS deixa de possuir fila ou estado próprio.
- Comandos do Discord passam a chamar a API local.
- GAIA chama os mesmos endpoints.
- Registrar a origem de cada ação:
  - `desktop`
  - `discord`
  - `gaia`
  - `system`

Fluxo unificado:

```text
Botão Próxima
Comando no Discord
“GAIA, pula essa”
        ↓
POST /v1/player/skip
        ↓
Player Core do ECHO
```

MCP deve entrar apenas depois dessa API estar estável. Ele será outro adaptador, nunca a autoridade do player.

## Fase 9 - Biblioteca e experiência ampliada

Somente após o núcleo estar estável:

- Playlists.
- Álbuns e artistas.
- Favoritos.
- Histórico detalhado.
- Letras sincronizadas.
- Tocar semelhantes.
- Rádio baseada em faixa ou artista.
- Busca unificada.
- Downloads ou cache opcional.
- Integração com controles de mídia do Windows.

Cada recurso deve possuir orçamento explícito de memória, cache e tarefas em segundo plano.

## Fase 10 - Teste prolongado e otimização

Cenários:

- Duas, oito e vinte e quatro horas tocando.
- Mil skips automatizados.
- Provider lento ou desconectado.
- MPV encerrado inesperadamente.
- Desktop aberto e fechado repetidamente.
- Reinício do ECHO durante uma fila.
- Duas interfaces conectadas simultaneamente.
- Biblioteca e histórico grandes.

Medir:

- RAM privada por processo.
- CPU média e picos.
- GPU dedicada e compartilhada.
- Threads e handles.
- I/O de disco.
- Requisições de rede.
- Tempo até iniciar o áudio.
- Latência dos comandos.
- Crescimento de cache.
- Processos órfãos.

Nenhuma nova fase deve começar se houver vazamento de memória ou atividade ociosa inexplicada.

## Definição de pronto do MVP

O MVP estará concluído quando:

- O ECHO tocar música sem Discord e sem Desktop.
- Desktop, GAIA e ERIS controlarem a mesma fila.
- Fechar o Desktop não interromper o áudio.
- O ECHO escolher `Track` sem conhecer a fonte final.
- O resolver recuperar streams expirados.
- Fila e posição sobreviverem a reinicializações.
- A inteligência existente não sofrer regressões.
- Os limites de CPU e memória forem cumpridos em build de produção.
- Nenhum código GPL ou AGPL dos projetos estudados tiver sido copiado.

## Ordem resumida

```text
benchmark
   ↓
domínio musical
   ↓
SQLite
   ↓
Player Core
   ↓
MPV
   ↓
Source Resolver
   ↓
API local
   ↓
ECHO Desktop
   ↓
ERIS e GAIA
   ↓
recursos avançados
   ↓
otimização final
```
