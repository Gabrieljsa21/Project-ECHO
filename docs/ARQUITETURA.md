# Arquitetura do Project ECHO

Satélite determinístico do Modo DJ da GAIA - segue o mesmo padrão de extração do
Project HESTIA/Project MOIRAI: processo próprio, sem UI, ponte HTTP simples
(`BaseHTTPRequestHandler`, sem framework), sem loop de manutenção (a GAIA decide
QUANDO chamar). Baseado na especificação completa em
`Project G.A.I.A/Project ECHO.md`.

## Por que um satélite, e não uma feature dentro da GAIA

Mesmo raciocínio do HESTIA/MOIRAI: o ranking musical é puramente determinístico
(seção 19 do ECHO_SPEC - "não depender exclusivamente do LLM pra escolher música"),
não depende de decisão em tempo real da persona, e tem uma superfície de API externa
própria (provedor musical) que não precisa de credencial/lógica misturada ao
processo principal. O que FICA do lado da GAIA é justamente o que precisa da persona:
explicabilidade em linguagem natural (seção 13), apresentação do Radar (seção 7.4),
interpretação de feedback em linguagem natural, e o Agendador Diário decidindo a
cadência semanal.

## Separação de responsabilidades (`echo/core/`)

🔥 **Tudo por pessoa desde 2026-08-26** (`discord_user_id` como primeiro
parâmetro em praticamente toda função) - Modo Música é social (qualquer
membro do servidor pode tocar/avaliar), então perfil/pool/histórico não
podem mais ser um documento único. Migração one-shot do formato antigo
(perfil único, sem chave de pessoa) pro `discord_user_id` real do dono
acontece sozinha na primeira carga depois do deploy (`DONO_DISCORD_ID_
MIGRACAO` em `perfil.py`, reaproveitado por `historico.py`/`radar.py`).

- **`perfil.py`** - gerencia preferências e pesos por pessoa (`data/perfil.json`,
  `{discord_user_id: {...}}`). Cadastro é manual nesta fase (artistas/gêneros
  favoritos e rejeitados, nível de descoberta) - sem histórico de reprodução
  real ainda (Fase 2, exceto import via Last.fm/lote, ver seção própria abaixo).
- **`recomendador.py`** - calcula candidatos e ranking. Score determinístico:
  `compatibilidade*0.50 + relevância*0.25 + descoberta*0.15 + exploração*0.10`
  (seção 6/19 do ECHO_SPEC) na base ("equilibrado"), com exclusão total (score
  negativo) pra repetição recente e artista EXPLICITAMENTE rejeitado
  (`disliked_artists`, ação deliberada - 🔥 desde 2026-08-27, um 👎 numa faixa
  avulsa NUNCA bloqueia o artista inteiro, ver "Pool pessoal pré-calculado"
  abaixo).
  `calcular_score`/`ranquear`
  aceitam `penalidades_sessao` opcional (dict `"artista::nome"`/`"genero::nome"`
  -> contagem) - reduz score de quem já apareceu demais NUMA sessão contínua do
  Modo Música, sem esperar o dedup exato de faixa (evita "sempre o mesmo
  artista 3x seguidas" mesmo quando cada faixa em si é diferente).
  - 🔥 **Nível de descoberta influencia os pesos de verdade (2026-09-06,
    seção 16 do ECHO_SPEC)** - `pesos_efetivos(discovery_level)` desloca peso
    entre compatibilidade e descoberta/exploração (relevância fica fixa - ficar
    sabendo o que tá bombando não depende de quanto o usuário quer fugir da
    própria bolha); `discovery_level=0.5` (padrão) preserva os pesos base
    acima exatamente. `0.0` (Conservador) zera descoberta/exploração de vez;
    `1.0` (Explorador) dobra a soma de descoberta+exploração às custas de
    compatibilidade. `calcular_score` lê `perfil["discovery_level"]` em vez
    dos pesos fixos - mesmo motor, sem perfil separado (não é sobre o score
    absoluto de UM candidato subir, é sobre um candidato obscuro/de descoberta
    passar a RANQUEAR acima de um mainstream do mesmo gênero quando o usuário é
    Explorador, ver `tests/test_recomendador.py`). Antes, `discovery_level` só
    era persistido no perfil (`perfil.py`) sem efeito nenhum aqui.
- **`radar.py`** - gera a seleção semanal: aplica a composição padrão (5
  compatibilidade / 3 relevância / 2 descoberta / 1 exploração pra 10 músicas, seção
  7.3) com diversidade (máx. 1 faixa por artista) e um preenchimento em RODÍZIO entre
  categorias quando alguma fica sem candidato suficiente - nunca um top-up genérico
  por score puro, que deixaria a categoria de maior peso (compatibilidade) engolir
  sozinha toda folga das demais. Depois de selecionar a edição da semana, chama
  `pool.gerar_pool_incremental` com a lista RANQUEADA completa (antes da
  curadoria de diversidade) - reaproveita a mesma rodada de descoberta pro pool
  do `/caos`, zero chamada de rede extra.
- **`pool.py`** (novo, 2026-08-26) - reservatório pessoal maior (100-300
  candidatos, `TAMANHO_ALVO`) que o `/caos`/continuação consomem AO VIVO sem
  rede, ver seção dedicada abaixo.
- **`feedback.py`** - dois níveis BEM diferentes de sinal (pedido do usuário:
  "👍/👎 representam sinais fortes e permanentes... pular cedo, ouvir até o
  final são sinais fracos e acumulativos"):
  - **Forte** (`processar_feedback`/`processar_feedback_ao_vivo`, 👍/👎
    explícito) - ajuste maior de peso de gênero (`AJUSTE_POSITIVO=0.08`/
    `AJUSTE_NEGATIVO=-0.12`), aplicado na hora, delegado pra `perfil.
    ajustar_peso_genero`. Sempre chama `pool.remover_track` (só a faixa
    EXATA, nunca o artista inteiro - 2026-08-27, pedido do usuário: "um 👎
    em 1 musica n pode condenar todas desse artista. Assim como o like n
    aprova todas tbm, algumas eu gosto e outras nao"; `pool.
    invalidar_relacionados`, que removia o artista inteiro num 👎, foi
    removido por esse mesmo motivo).
  - **Fraco** (`processar_feedback_passivo`, tempo de escuta medido pelo
    ERIS) - um evento isolado NUNCA ajusta peso sozinho; só depois de
    `MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR=3` sinais consistentes na mesma
    direção pro mesmo artista (`historico.contar_eventos_fracos_recentes`)
    é que vira um ajuste PEQUENO (`AJUSTE_PASSIVO_POSITIVO=0.03`/
    `AJUSTE_PASSIVO_NEGATIVO=-0.03`). Todo evento é logado bruto
    (`historico.registrar_evento_escuta`) mesmo quando não ajusta nada -
    dado guardado pra refinar o algoritmo depois sem ter perdido histórico.
- **`historico.py`** - evita repetição (seção 8) e registra feedback; redescoberta
  do Radar semanal permitida só após `DIAS_REDESCOBERTA` (90 dias, seção 9). Ganhou
  `foi_apresentada_alguma_vez` (SEM janela de dias - exclusão PERMANENTE, usada só
  pelo pool) e `obter_aprovadas`/`obter_desaprovadas` (dedup pela aparição mais
  recente de cada faixa). Log separado de eventos passivos em `eventos_escuta.json`.
- **`continuacao.py`** - ver seção "Continuação ao vivo" abaixo.

## Provedor musical (`echo/providers/`)

Abstração (`ProvedorMusical`) desacoplada de propósito (seção 17/princípio 7 da
seção 31 - "o núcleo do Modo DJ deve sobreviver à troca da integração musical").
Métodos: `buscar_faixa`, `obter_faixas_do_artista`, `obter_faixas_por_tag`,
`obter_lancamentos_novos`, `obter_faixas_em_alta`, `obter_reproduzidas_recentemente`,
`obter_top_faixas_usuario`, `obter_top_artistas_usuario`, `criar_playlist`,
`adicionar_faixa_playlist`, `tocar_faixa`.

### Bug real: `obter_faixas_por_tag` sempre devolveu lista vazia (2026-08-26)

Investigando "usei /caos... ela tocou apenas 1 musica, n mandou mais"
(também explicava a repetição relatada antes) - reproduzido: pedir
continuação semeada por "Olivia Rodrigo" devolvia `{"proxima": null}`.
Causa raiz teve DUAS camadas: (1) o usuário tinha dado 👎 numa faixa dela
antes, o que bloqueia CORRETAMENTE o artista inteiro
(`historico.artista_tem_feedback_negativo`) - comportamento certo; (2)
mas o candidato de FALLBACK por gênero (`obter_faixas_por_tag`, usado
quando o artista-semente está bloqueado) sempre devolvia lista vazia,
silenciosamente, então não sobrava candidato nenhum pra sugerir. Causa
raiz de (2): `tag.gettoptracks` devolve a lista dentro de `{"tracks":
{"track": [...]}}`, mas o código lia `{"toptracks": {...}}` (a chave de
`artist.gettoptracks`, um endpoint DIFERENTE - cada método do Last.fm
usa um wrapper próprio, apesar do nome parecido). Bug existia desde que
o método foi escrito - afetava TODA sugestão "por gênero" (descoberta/
exploração) do Radar semanal E da continuação ao vivo, não só esse caso.
Corrigido (`echo/providers/lastfm.py`), teste novo trava a chave certa.

### Por que Last.fm (não Spotify) - decisão de 2026-08-25

A implementação de referência original usou o Spotify (Client Credentials, sem
login), mas uma mudança de política da própria Spotify em fevereiro/março de 2026
(1) passou a exigir **assinatura Premium ATIVA** só pra manter o app de
desenvolvedor funcionando (se o Premium expirar, o app para) e (2) **removeu o
endpoint de "novos lançamentos"** (`GET /browse/new-releases`) sem substituto
oficial, junto com a busca em lote de artistas. Isso quebrava justamente a
"busca de lançamentos" da Fase 1, e criava um vínculo de pagamento recorrente
indesejado pra um projeto pessoal.

`ProvedorLastfm` (`providers/lastfm.py`) substituiu o Spotify: API gratuita, sem
assinatura, sem login de usuário, chave gerada em 2 minutos. Como a Fase 1 nunca
toca música de verdade (isso só entra na Fase 3, com login de usuário num
serviço de streaming), o Last.fm - que é puramente um serviço de
metadado/scrobbling - encaixa melhor que o Spotify já encaixava:
- `chart.gettoptracks` (chart global) alimenta `obter_lancamentos_novos` -
  aproximação honesta de "relevância atual" (Last.fm não tem conceito de data de
  lançamento, só de popularidade de reprodução).
- `artist.gettoptracks` alimenta `obter_faixas_do_artista` - substitui o hack
  `buscar_faixa('artist:"X"')` que a versão Spotify precisava, com um endpoint
  dedicado de verdade.
- `tag.gettoptracks` alimenta `obter_faixas_por_tag` (NOVO, não existia na
  versão Spotify) - candidato dedicado por gênero preferido, alimentando
  descoberta/exploração melhor do que só sobras do chart global.
- Popularidade normalizada em escala LOGARÍTMICA de `listeners` (contagem bruta,
  sem teto) pra 0-100, já que o Last.fm não tem um score de popularidade oficial
  como o Spotify tinha - aproximação documentada em `lastfm.py`.

### Histórico real de escuta e cadastro em lote (2026-08-25, Fase 2 antecipada)

Pedido do usuário: "ela consegue absorver minhas playlist do spotfy p saber
meus gostos?" - resolvido com 2 caminhos, sem precisar de OAuth do Spotify:

1. **`LASTFM_USERNAME` vinculado** (opcional, `.env`) - se o usuário já usa
   scrobbling (Spotify -> Last.fm), `obter_top_artistas_usuario`/
   `obter_top_faixas_usuario`/`obter_reproduzidas_recentemente` usam
   `user.gettopartists`/`user.gettoptracks`/`user.getrecenttracks` pra ler o
   histórico REAL de escuta - `core.perfil.importar_favoritos_do_historico`
   pesa cada gênero pela POSIÇÃO no ranking real (mais tocado = mais peso),
   nunca diminui um peso já mais alto (não apaga ajuste fino feito por
   feedback manual). **Achado real ao testar**: conexão scrobbling pode
   existir mas estar vazia (`playcount: 0`) se o usuário não tiver escutado
   nada desde que ativou - nesse caso não há dado real pra importar, e o
   sistema não inventa nada, só devolve lista vazia.
2. **Cadastro em lote sem scrobbling** (`/perfil/importar_artistas`) - o
   usuário cola uma playlist/lista de artistas em conversa, a LLM extrai os
   nomes REAIS do texto (tag `<CADASTRAR_ARTISTAS:nome1|nome2|...>` no repo
   da GAIA) e o ECHO resolve o gênero de cada um automaticamente
   (`provedor.resolver_generos`) - reaproveita `adicionar_artista_favorito`
   (peso FLAT por artista, diferente do caminho 1 - a ordem de uma playlist
   colada não representa "mais tocado primeiro" de verdade, seria desonesto
   fingir que representa).

Métodos de playlist/playback (Fase 3 - Last.fm não faz streaming, vai exigir
um provedor DIFERENTE, ex.: Spotify com OAuth de usuário de verdade) levantam
`ProvedorIndisponivel` com mensagem clara.

`ProvedorIndisponivel` é a única forma de falha esperada - nunca vira dado
inventado (seção 27: "nunca inventar músicas, artistas, datas ou métricas quando o
provedor não retornar informação confiável"). Sem credencial configurada, `GET
/status` já reporta isso antes de qualquer tentativa de Radar.

## Contrato HTTP (porta 8774, `echo/api_bridge.py`)

🔥 Toda rota exige `discord_user_id` (query pra GET, corpo pra POST) desde
2026-08-26 - omitido abaixo por brevidade em toda rota, exceto onde o
formato do parâmetro importa.

- `GET /status` - `{"provedor_configurado": bool, "username_vinculado": bool}`
  (única rota que NÃO exige `discord_user_id` - não é específica de pessoa).
- `GET /perfil` - perfil musical completo dessa pessoa.
- `GET /perfil/aprovados` / `GET /perfil/desaprovados` (novo, 2026-08-26) -
  `{"aprovadas": [...]}`/`{"desaprovadas": [...]}`, lista curada por
  feedback explícito (`/musica aprovadas`/`/musica desaprovadas` do ERIS).
- `GET /perfil/voto?titulo=&artista=` (novo, 2026-08-27) -
  `{"voto": "positivo"|"negativo"|null}` - se essa faixa já foi avaliada
  antes por essa pessoa (`historico.obter_voto`). Usado pelo ERIS pra
  mostrar "(👍)"/"(👎)" na mensagem de "tocando agora".
- `POST /perfil/artista_favorito` `{"nome", "genero"}` - também remove de
  rejeitados se estava lá.
- `POST /perfil/artista_rejeitado` `{"nome"}`.
- `POST /perfil/genero` `{"nome", "peso"}` - define (não ajusta) o peso de um
  gênero.
- `POST /perfil/discovery_level` `{"valor"}` (0.0-1.0).
- `GET /radar/atual?forcar=0|1` - devolve o último Radar já gerado hoje (a menos que
  `forcar=1`); gera um novo coletando chart global + faixas dos artistas favoritos +
  faixas por gênero preferido, e alimenta o pool incremental dessa pessoa
  (`pool.gerar_pool_incremental`). 503 com `{"erro", "radar": []}` se o provedor
  não estiver disponível.
- `GET /radar/historico?limite=N` - últimas N recomendações (mais recente primeiro).
- `GET /em_alta` (novo, 2026-09-06, seção 3.3 do ECHO_SPEC) - músicas
  atualmente relevantes, sem filtrar por compatibilidade pessoal. Mesma
  coleta do Radar (`obter_lancamentos_novos`), diversidade (máx. 1 por
  artista) e dedup de 90 dias compartilhado com o Radar. 503 com `{"erro",
  "em_alta": []}` se o provedor não estiver disponível.
- `GET /redescobertas?quantidade=N` (novo, 2026-09-06, seção 9 do ECHO_SPEC) -
  faixas aprovadas (👍) sem aparecer (recomendadas OU realmente ouvidas) há
  pelo menos 180 dias, mais esquecida primeiro. `quantidade` padrão 1
  (frequência deve ser baixa, seção 9). Só dados locais, nunca chama o
  provedor - não pode dar 503.
- `POST /perfil/importar_historico` `{"limite"}` - seed do perfil a partir do
  histórico real de escuta (`LASTFM_USERNAME` obrigatório). 503 se não vinculado.
- `POST /perfil/importar_artistas` `{"nomes": [...]}` - cadastro em lote de
  artistas favoritos (gênero resolvido automaticamente por artista).
- `POST /radar/feedback` `{"track_id", "feedback", "genero"}` - `feedback` é
  `"positivo"` ou `"negativo"`; `genero` vem de quem está mandando (a GAIA reenvia o
  que recebeu junto com a faixa no Radar).
- `POST /radar/proxima` `{"artista_atual", "titulo_atual", "excluir", "penalidades_sessao"}`
  - continuação ao vivo (ver seção abaixo). `excluir`: lista de
  "artista::titulo" já tocados na sessão atual. `penalidades_sessao` (opcional):
  dict de diversidade, ver `recomendador.py` acima.
- `POST /radar/semente` `{"excluir", "penalidades_sessao"}` - sugestão de
  PARTIDA sem faixa atual pra semear (`/caos` do ERIS, ver seção abaixo).
- `POST /radar/feedback_ao_vivo` `{"artista", "titulo", "feedback"}` -
  botões 👍/👎 na mensagem de "tocando agora" do Modo Música (ERIS,
  2026-08-26). Diferente de `/radar/feedback`, não exige `track_id`
  pré-existente (a faixa pode nunca ter passado pelo Radar) - cria a
  entrada no histórico na hora se faltar, e resolve o gênero sozinho via
  `provedor.resolver_generos` (o ERIS só sabe artista/título, não gênero).
  Sempre tira a faixa exata do pool (`pool.remover_track`), nunca o
  artista inteiro.
- `POST /radar/feedback_passivo` `{"artista", "titulo", "fracao_tocada",
  "pulado", "momento_do_skip"}` (novo, 2026-08-26) - sinal fraco medido pelo
  ERIS (tempo de escuta). Devolve `{"ajustou_peso": bool, "negativo": bool}`
  - a maioria das chamadas não ajusta nada (evento isolado), só devolve
  `True` depois de um padrão consistente (ver `feedback.py` acima).

## Pool pessoal pré-calculado (`pool.py`, 2026-08-26)

Pedido do usuário, investigando "eu mandei varias playlists, ela n se
baseia nelas como meu gosto?": "prefiro pré-calcular o repertório do que
reconstruir recomendações toda vez que o comando é executado". Diferente do
Radar semanal (lote FECHADO de 10 músicas curadas com diversidade pra 1
edição), o pool é um reservatório MAIOR (100-300 por pessoa, `TAMANHO_ALVO`)
que `/radar/semente`/`/radar/proxima` consomem AO VIVO - **zero chamada de
rede no caminho crítico** entre uma faixa acabar e a próxima começar.

- **Nunca recriado do zero** (pedido explícito do usuário) -
  `gerar_pool_incremental` funde com o pool existente: atualiza score de quem
  já estava lá, adiciona os novos, remove quem já foi VOTADA
  (`historico.foi_votada`) ou não coube no `TAMANHO_ALVO` (mantém só os de
  maior afinidade).
- **Reaproveita a descoberta semanal do Radar** - `radar.gerar_radar` chama
  `gerar_pool_incremental` logo depois de ranquear, com a lista COMPLETA
  (antes da curadoria de diversidade da edição fechada) - o pool nunca
  dispara sozinho uma busca no provedor; quem varre o Last.fm continua
  sendo só o Radar (1x/semana) ou a descoberta de emergência abaixo
  (fallback raro).
- **Cada candidato guarda por que foi recomendado** (`origem`, `artista_
  semente`, `afinidade`, `descoberto_em`) - explicabilidade/depuração.
- `consumir_proxima` - SORTEIA entre as `TAMANHO_TOPO_SORTEIO` (5) de maior
  score (`afinidade + boost de proximidade da semente - penalidade de
  diversidade de sessão`) e registra em `historico` (reason="pool", sem
  voto ainda) - alimenta o dedup de 90 dias do Radar semanal. 🔥 **NÃO
  remove do pool** (2026-08-26, pedido do usuário: "Musicas sem voto não
  saem do pool") - tocar sem avaliar não é sinal de rejeição nem de
  aprovação; dedup de CURTO prazo (não repetir na mesma sessão) já é
  resolvido por `excluidos_sessao`, de quem chama. 🔥 **Sorteio, não
  `max()` estrito** (2026-08-27, achado real em produção: com o pool
  cheio, `/caos` em sessões NOVAS - exclusão vazia - sempre devolvia a
  MESMA faixa de maior afinidade, já que ela nunca sai do pool sozinha) -
  `random.choice` entre o topo preserva "prefere afinidade alta" sem virar
  sempre a mesma escolha.
- `remover_track` - sai do pool assim que a faixa EXATA recebe um voto
  (👍 ou 👎, chamado por `feedback.py` em toda avaliação explícita) - só
  ELA, nunca mexe em mais nada do mesmo artista. 🔥 **`invalidar_
  relacionados` removido (2026-08-27)** - existia até então pra remover
  TODO o artista do pool num 👎, mas o usuário apontou que isso "condena"
  faixas do mesmo artista que ele nunca ouviu/avaliou: "um 👎 em 1 musica
  n pode condenar todas desse artista. Assim como o like n aprova todas
  tbm, algumas eu gosto e outras nao". Voto (qualquer direção) agora fica
  estritamente por FAIXA - o único jeito de rejeitar um artista inteiro é
  a ação explícita e deliberada `perfil.adicionar_artista_rejeitado`
  (`disliked_artists`, seção "Contrato HTTP"), nunca inferido de um voto
  numa única música.

### Reabastecimento de emergência em background (2026-08-28)

Achado real investigando "/caos esta tocando apenas as musicas aprovadas
[depois de um tempo]": o pool pessoal de um usuário tinha só **29
candidatas** sem voto (bem abaixo do `TAMANHO_ALVO`=200), enquanto o ERIS
mantém até ~110 faixas excluídas de uma vez numa sessão longa (histórico de
sessão até 50 + fila lógica reservada até 50 + streams prontos até 10, ver
`ARQUITETURA.md` do [Project ERIS](../../Project-ERIS)). Assim que as 29
eram tocadas/reservadas, `consumir_proxima` passava a devolver `None`
sempre - a Camada 1 (pool) ficava presa vazia pelo resto da sessão inteira,
e o `/caos` nunca saía da Camada 2 (aprovadas) até a próxima rodada semanal
do Radar regenerar o pool.

Corrigido com uma fonte de descoberta NOVA, independente do Radar semanal
(pedido explícito do usuário - "a geração semanal pode continuar existindo
como manutenção preventiva, mas não pode ser a única forma de abastecer o
pool"):

- `consumir_proxima` calcula `candidatos_validos` (pool menos
  `excluidos_sessao` - exatamente "quantidade disponível" pro usuário) e,
  se ficar abaixo de `MINIMO_DISPONIVEL` (20), dispara `reabastecer_pool`
  numa THREAD separada (`_acionar_reabastecimento_background`) - o ECHO é
  um `HTTPServer` de thread única (`api_bridge.py`), então "não bloquear a
  reprodução" aqui significa literalmente não segurar essa thread com
  chamadas de rede. A checagem NÃO impede de devolver o que ainda sobra no
  pool - só garante que uma pesquisa nova já começou.
- `reabastecer_pool` usa os ARTISTAS das músicas **aprovadas** do usuário
  como sementes (pedido explícito - fonte deliberadamente diferente do
  perfil geral de favoritos/gêneros que já alimenta o Radar semanal),
  busca até `LIMITE_FAIXAS_POR_SEMENTE` (15) faixas por artista
  (`obter_faixas_do_artista`), filtra quem já está no pool/já foi votada/já
  está excluída pela sessão atual, rankeia com o MESMO motor determinístico
  (`recomendador.ranquear`) e tenta juntar `META_REABASTECIMENTO` (30)
  candidatas novas, avançando pra próxima semente se uma não render o
  suficiente. Dedup por `url_lastfm` (aproximação de "ID da plataforma" -
  Last.fm não tem um ID numérico estável de faixa) com fallback pro
  `artista::título` normalizado de sempre.
- **Incremental de verdade** - grava no `pool_musical.json` a cada semente
  resolvida (não acumula em memória até o fim da busca inteira), então uma
  sessão presa na Camada 2 já pode voltar a consumir do pool assim que a
  primeira leva entrar, sem esperar todas as sementes.
- `_reabastecendo` (set + lock) impede disparar 2 pesquisas em paralelo pro
  MESMO usuário - o ERIS chama `consumir_proxima` várias vezes seguidas
  reabastecendo a própria `fila_logica`, então sem essa guarda cada chamada
  nessa janela criaria uma thread nova.
- `_lock_arquivo` (novo) protege toda leitura-modifica-grava de
  `pool_musical.json` - antes desta feature só a thread principal do
  `HTTPServer` mexia nesse arquivo (single-threaded, sem risco de corrida);
  agora a thread de reabastecimento pode escrever ao mesmo tempo que um
  voto/feedback ao vivo (`remover_track`) ou uma geração semanal
  (`gerar_pool_incremental`) - sem o lock, um load-modifica-grava
  concorrente perderia a escrita de um dos dois lados.
- Log de cada rodada (`print`, prefixo `[ECHO]`): quando começou, quanto
  levou, quantas faixas foram analisadas/descartadas/adicionadas -
  validado ao vivo contra a API real do Last.fm (pool do dono foi de 29
  pra 59 candidatas numa rodada de ~3s).
- Nenhuma mudança precisou entrar em `continuacao.py` - a Camada 2
  (aprovadas) já era só um fallback consultado quando a Camada 1 devolve
  `None`; assim que o reabastecimento grava candidatas novas no arquivo, a
  PRÓXIMA chamada a `consumir_proxima` já enxerga isso e volta a priorizar
  o pool sozinha, sem nenhum estado de sessão pra resetar.

## Continuação ao vivo (Modo Música do ERIS, 2026-08-25)

Pedido do usuário: "quero q alguem seja meu dj exclusivo... qnd eu pedir uma
musica, ele continue tocando outras em sequencia na mesma vibe". Diferente
do Radar semanal (lote fechado de 10 músicas), `echo/core/continuacao.py`
devolve UMA sugestão por vez, semeada pela faixa que está tocando AGORA
numa call de verdade (quem toca é o [Project ERIS](../../Project-ERIS) -
o ECHO nunca sabe o que é YouTube/Discord, só devolve `{"artista",
"titulo"}`).

🔥 **Reescrito (2026-08-26) pro pool pré-calculado** - fallback em camadas
(pedido do usuário): **pool pessoal → aprovadas dessa pessoa → descoberta
emergencial síncrona (rede, só quando as duas primeiras falharem) → None**.
As camadas 1/2 não fazem chamada de rede nenhuma; a camada 3 (`sugerir_
proxima`) trata o artista/gêneros da faixa atual como preferência FORTE só
pra essa sugestão (perfil efetivo, cópia em memória, nunca persistida) -
mesmo raciocínio de antes, agora só acionado como último recurso.

**`/caos` do ERIS (2026-08-26)** - pedido do usuário: "ERIS entra no canal
de voz do usuário e inicia uma sessão musical contínua... sem exigir
artista, gênero, música ou qualquer outra referência inicial".
`sugerir_semente` segue a mesma cadeia de camadas (pool → aprovadas →
`obter_lancamentos_novos` como único fallback de emergência, sem boost
artificial de perfil). Funciona mesmo com perfil TOTALMENTE vazio - o
chart global sozinho já supre candidato via relevância/exploração na
camada 3, e o pool geralmente resolve sozinho depois da 1ª rodada semanal.

### Bug real: `/caos` repetia a mesma música em sessões diferentes, com o pool vazio (2026-08-27)

Confirmado em produção: `/caos` chamado 3x seguidas (3 sessões separadas)
devolveu "Counting Stars - OneRepublic" como semente TODA vez. Causa raiz:
o pool pessoal do dono ainda estava com **0 candidatos** (nunca gerado
desde a migração pro formato por pessoa - só populado por uma rodada do
Radar semanal ou `forcar=1`), então a camada 1 sempre falhava e caía pra
camada 2 (aprovadas). `_primeira_aprovada_nao_excluida` (antigo nome)
sempre devolvia a PRIMEIRA entrada não excluída da lista - como cada
`/caos` é uma sessão NOVA (exclusão de sessão reseta), e "Counting Stars"
era a primeira faixa aprovada em ordem de inserção no histórico, ela
vencia sempre. Renomeada pra `_aprovada_aleatoria_nao_excluida` -
`random.choice` entre TODAS as elegíveis, não só a primeira. O problema
de fundo (pool vazio) se resolve sozinho assim que o Radar rodar 1x pro
dono; o sorteio é só pra a camada de emergência não parecer travada
enquanto isso não acontece.

**Latência (2026-08-26, achado real: "Caos esta demorando para iniciar")**
- antes desta reescrita, `/radar/semente` chamava `_coletar_candidatos` com
até 16 chamadas sequenciais ao provedor (~9.8s), bloqueando uma interação
AO VIVO do Discord. Com o pool, o caminho NORMAL não faz rede nenhuma -
praticamente instantâneo; só a camada 3 (rara) ainda paga esse custo,
reduzido separadamente (`max_artistas=1, max_generos=3, limite_geral=15`
dentro de `continuacao.py`, não mais em `api_bridge.py::_coletar_
candidatos`, que agora só serve o Radar semanal).

## Persistência (`data/`, gitignored)

`perfil.json`, `historico_recomendacoes.json`, `eventos_escuta.json`,
`radar_estado.json`, `pool_musical.json` - todos no formato `{discord_user_id:
{...}}` desde 2026-08-26 (migração one-shot do formato antigo na primeira
carga, ver `DONO_DISCORD_ID_MIGRACAO`). Lidos do disco a cada chamada (nunca
cacheados em memória entre requests), mesmo padrão já usado no HESTIA/MOIRAI
depois do bug real de cache stale documentado lá
(`Project G.A.I.A/assistant/docs/CORRECOES.md`).

## O que fica pendente pra Fase 2/3 (ver `TODO.md`)

Peso comportamental contínuo (hoje o histórico do Last.fm só vira seed
inicial do perfil, não ajusta com o tempo), Playlist Descobertas automática
(o playback de música em si já existe via ERIS/YouTube fora da abstração de
provedor do ECHO - mas SALVAR uma playlist gerenciada continua exigindo um
provedor com biblioteca/playlist de usuário, ex.: Spotify com OAuth),
recomendações contextuais. `criar_playlist`/`adicionar_faixa_playlist`/
`tocar_faixa` na abstração `ProvedorMusical` continuam sem implementação -
o playback de verdade achou outro caminho (ERIS busca no YouTube direto,
nunca precisou dessa interface).

Nível de descoberta influenciando o ranking, Em Alta dedicado e
Redescobertas dedicadas (todos resolvidos em 2026-09-06, ver seções acima)
existem no ECHO mas ainda sem consumidor do lado da GAIA - `echo_client.py`
(repo dela) ainda não tem os wrappers de `/em_alta`/`/redescobertas`, e
nenhuma tag/comando os expõe em conversa. Mesmo padrão de outros endpoints já
expostos "pra um Painel futuro" (ver `integrations/echo_client.py` no repo da
GAIA) - fica pra quando a integração do lado dela fizer sentido.

## Integração com a GAIA (feita no repo dela)

`integrations/echo_client.py` (mesmo padrão de `hestia_client.py`) + tag
`<RADAR_MUSICAL>` (`core/tools/handlers.py`) pra o usuário poder pedir o Radar em
conversa, `garantir_echo_rodando()` subindo o processo automaticamente no boot
da GAIA (`integrations/iris_bridge.py`, mesmo padrão do ERIS), e entrega
PROATIVA semanal via Agendador Diário
(`run.py::_verificar_e_executar_radar_musical_semanal`, opt-in, desligada por
padrão) - toggle + horário configuráveis no Painel (Notificações -> "🎧 Radar
Musical"). A entrega proativa usa `resumir_com_ia` pra apresentar a seleção com
a persona (nunca inventa música/artista - só sintetiza a partir do Radar real);
a tag sob demanda continua disponível independente desse toggle, gatilhada só
por `echo_client.esta_configurado()`.
