# Changelog

## [Unreleased]

### Novidades
- **`iniciar_echo.bat`/`iniciar_echo_oculto.vbs` (2026-09-01)** - roda o ECHO escondido via `pythonw.exe`, sem console. Usado pelo item "ECHO" da categoria "Projects" do IRIS (ver `Project-IRIS/ARQUITETURA.md`). Ver `README.md`.
- **3 pendências de Fase 2 do ECHO_SPEC resolvidas (2026-09-06)**, encerrando `Project ECHO.md` (spec original, removido - todo o conteúdo útil dele já está implementado ou documentado no `TODO.md`):
  - **Nível de descoberta influenciando o ranking de verdade** - `core/recomendador.py` ganhou `pesos_efetivos(discovery_level)`: desloca peso entre compatibilidade e descoberta/exploração (relevância atual fica fixa), preservando os pesos base de sempre em 0.5 ("equilibrado"). Antes, `discovery_level` só era persistido no perfil sem efeito nenhum no ranking.
  - **Em Alta** (seção 3.3) - `core/em_alta.py` (`obter_em_alta`) e `GET /em_alta`: reaproveita a mesma coleta de "lançamentos" que já alimentava o Radar (`obter_lancamentos_novos`), mas numa apresentação própria sem filtrar por compatibilidade pessoal (é sobre o que tá bombando agora, não sobre o gosto de quem pergunta), com diversidade (máx. 1 faixa por artista) e o mesmo dedup de 90 dias do Radar.
  - **Redescobertas** (seção 9) - `core/redescobertas.py` (`obter_redescobertas`) e `GET /redescobertas`: identifica faixas aprovadas (👍) que não aparecem (recomendadas OU realmente ouvidas, via `historico.obter_ultima_aparicao`) há pelo menos 180 dias, mais esquecida primeiro. Só dados locais, sem chamada ao provedor.

### Corrigido
- **`/caos` ficava preso tocando só as aprovadas depois que o pool pessoal esgotava (2026-08-28)** - achado real: pool de um usuário tinha só 29 candidatas sem voto (bem abaixo do alvo de 200), e o ERIS mantém até ~110 faixas excluídas de uma vez numa sessão longa - assim que as 29 eram tocadas/reservadas, a Camada 1 (pool) ficava vazia pelo resto da sessão até a próxima rodada semanal do Radar. Corrigido com reabastecimento de emergência em BACKGROUND (thread separada, nunca bloqueia o `/caos`): `pool.consumir_proxima` dispara `pool.reabastecer_pool` assim que sobram menos de 20 candidatas disponíveis, usando os artistas das músicas aprovadas do usuário como semente pra buscar até 30 faixas novas no Last.fm, gravadas no pool incrementalmente (não só no final). Validado ao vivo contra a API real - pool foi de 29 pra 59 candidatas numa rodada de ~3s. Ver `ARQUITETURA.md`.

## [0.1.0] - 2026-08-25 a 2026-08-27: Modo DJ completo - Radar Musical, pool por pessoa, Modo Música ao vivo (PRs #1 a #10)

### Novidades
- **Repositório criado (Fase 1 do MVP, 2026-08-25)** - Project ECHO, Modo DJ da GAIA,
  baseado na especificação completa em `Project G.A.I.A/Project ECHO.md`. Perfil
  musical persistente (`echo/core/perfil.py`), motor de ranking determinístico
  (`echo/core/recomendador.py`, pesos 50/25/15/10), geração do Radar Musical semanal
  com diversidade e preenchimento em rodízio entre categorias
  (`echo/core/radar.py`), histórico de recomendações com dedup/redescoberta de 90
  dias (`echo/core/historico.py`), feedback 👍/👎 com ajuste incremental de peso
  (`echo/core/feedback.py`), provedor abstrato desacoplado
  (`echo/providers/__init__.py`). Ponte HTTP na porta 8774 (`echo/api_bridge.py`),
  guarda de instância única na porta 8775 (`echo/main.py`), sem loop de manutenção
  próprio (mesmo padrão do HESTIA - a GAIA decide quando gerar o Radar).
- **Integração completa com a GAIA** - `integrations/echo_client.py`, tag
  `<RADAR_MUSICAL>` (mesmo padrão de `<RECOMENDAR_ANIME>`), e
  `garantir_echo_rodando()` subindo o processo automaticamente no boot dela (mesmo
  padrão de ERIS/HESTIA/MOIRAI) - sem isso, `echo_client.esta_configurado()` nunca
  viraria `True` (precisa do ECHO já respondendo) e a tag nunca seria ensinada à
  LLM.
- **Provedor musical: Last.fm em vez de Spotify** (mesmo dia, achado real) - a
  implementação original usava Spotify (Client Credentials), mas uma mudança de
  política da Spotify em fevereiro/março de 2026 passou a exigir assinatura
  Premium ATIVA só pra manter o app funcionando e removeu o endpoint de "novos
  lançamentos" (`GET /browse/new-releases`) sem substituto. Trocado por
  `echo/providers/lastfm.py` - API gratuita, sem assinatura, sem login de usuário.
  Ganhou 2 métodos novos na abstração (`obter_faixas_do_artista`,
  `obter_faixas_por_tag`) que encaixam melhor no Last.fm do que o hack de busca
  usado antes pro Spotify. Ver `ARQUITETURA.md` pro detalhe completo da decisão.

22 testes automatizados (`tests/`) cobrindo perfil/histórico/radar/normalização de
popularidade, todos passando.

- **Validado contra a API real do Last.fm** (2026-08-25) - `LASTFM_API_KEY` real
  configurada pelo usuário, `GET /status` confirmou `provedor_configurado: true`
  e um Radar Musical real foi gerado com sucesso (10 músicas reais do chart
  global do Last.fm, ex.: "Creep" - Radiohead, "505" - Arctic Monkeys).
- **Cadência proativa semanal wireada** (2026-08-25, repo da GAIA) -
  `run.py::_verificar_e_executar_radar_musical_semanal`, entra no Agendador
  Diário (opt-in, desligado por padrão), toggle+horário no Painel
  (Notificações -> "🎧 Radar Musical"). Fase 1 do MVP fica **completa** - Radar
  Musical funciona sob demanda (`<RADAR_MUSICAL>`) E proativamente.
- **Importação de gosto musical (Fase 2 antecipada, 2026-08-25)** - pedido do
  usuário: "ela consegue absorver minhas playlist do spotfy p saber meus
  gostos?". 2 caminhos, sem OAuth do Spotify: (1) `obter_top_artistas_usuario`/
  `obter_top_faixas_usuario`/`obter_reproduzidas_recentemente` via
  `LASTFM_USERNAME` vinculado (histórico real de scrobbling) +
  `core.perfil.importar_favoritos_do_historico` (peso por posição no ranking
  real); (2) `POST /perfil/importar_artistas` - cadastro em lote colando uma
  playlist/lista (tag `<CADASTRAR_ARTISTAS>` no repo da GAIA), gênero
  resolvido automaticamente. **Achado real**: testado com a conta do usuário -
  scrobbling estava conectado mas com `playcount: 0` (sem escutar nada desde
  que ativou), então o caminho (1) veio vazio de propósito (não inventou
  dado); caminho (2) segue disponível pra esse caso. 27 testes automatizados,
  todos passando.
- **Continuação ao vivo - `POST /radar/proxima`** (2026-08-25, pedido do
  usuário: "quero q alguem seja meu dj exclusivo... qnd eu pedir uma
  musica, ele continue tocando outras em sequencia na mesma vibe") -
  `echo/core/continuacao.py`, uma sugestão por vez semeada pela faixa
  tocando agora (quem toca é o [Project ERIS](../../Project-ERIS), Modo
  Música novo, substitui o Jockie Music). Perfil efetivo em memória (nunca
  persistido) trata o artista/gêneros da faixa atual como preferência forte
  só pra essa sugestão. Dedup de sessão via parâmetro `excluir` (quem
  chama, o ERIS, mantém a lista do que já tocou na call) - resolve a
  queixa real do usuário sobre o Jockie repetir depois de um tempo. 32
  testes automatizados (5 novos), todos passando; validado ao vivo contra
  o Last.fm real (sugeriu corretamente outra faixa do mesmo artista,
  respeitando exclusão).
- **Sugestão de partida sem referência - `POST /radar/semente`** (2026-08-26,
  pedido do usuário: "ERIS entra no canal de voz do usuário e inicia uma
  sessão musical contínua... sem exigir artista, gênero, música ou qualquer
  outra referência inicial", comando `/caos` no ERIS) - `echo/core/
  continuacao.py::sugerir_semente`, ranqueia direto a mesma composição de
  candidatos do Radar semanal (chart global + artistas favoritos + gêneros
  preferidos) sem precisar de faixa atual, funciona mesmo com perfil
  totalmente vazio. 4 testes novos (36 no total), todos passando; validado
  ao vivo contra o Last.fm real com o perfil do usuário (sugeriu Radiohead,
  depois Maroon 5 ao excluir a primeira).
- **Feedback ao vivo - `POST /radar/feedback_ao_vivo`** (2026-08-26, pedido
  do usuário: "quando ela toca uma musica, podia aparecer botoes de like,
  dislike e next") - `echo/core/feedback.py::processar_feedback_ao_vivo`,
  mesmo ajuste incremental de gênero do feedback do Radar (+0.08/-0.12,
  nunca substitui o perfil), mas cria a entrada no histórico na hora se a
  faixa nunca passou pelo Radar (busca livre do usuário no Modo Música) e
  resolve o gênero sozinho - o ERIS só manda artista/título. 6 testes
  novos (42 no total), todos passando; validado ao vivo contra o Last.fm
  real (like e dislike na mesma faixa, segunda chamada atualiza a mesma
  entrada em vez de duplicar).

- **Perfil por pessoa + pool pré-calculado + feedback fraco/forte (2026-08-26)** -
  reescrita completa depois de investigar "eu mandei varias playlists, ela n se
  baseia nelas como meu gosto?": o `/caos` reconstruía recomendações do zero a
  cada chamada (rede ao vivo), amostrando só 1 artista favorito por vez. Agora:
  - **Tudo por `discord_user_id`** (`perfil.py`/`historico.py`/`radar.py` -
    migração one-shot do formato antigo pro dono real) - Modo Música é social,
    feedback de qualquer visitante não pode mais mexer no perfil do dono.
  - **Pool pessoal incremental** (`pool.py`, novo, 100-300 candidatos por
    pessoa) - reaproveita a MESMA rodada de descoberta semanal do Radar, zero
    chamada de rede extra; nunca recriado do zero (só funde/atualiza/remove).
    `/radar/semente` e `/radar/proxima` (`continuacao.py`, reescrito) agora
    consomem o pool primeiro - zero rede no caminho crítico. Fallback em
    camadas: pool pessoal → aprovadas dessa pessoa → descoberta emergencial
    síncrona → erro informado.
  - **Exclusão permanente** (`historico.foi_apresentada_alguma_vez`, sem
    janela de dias) - o `/caos` nunca repete uma faixa já apresentada pra
    essa pessoa, diferente do dedup de 90 dias do Radar semanal.
  - **Feedback fraco/forte** (`feedback.py`) - 👍/👎 continuam ajuste grande e
    imediato; tempo de escuta (skip cedo/ouviu quase inteira) vira sinal
    FRACO, só ajusta peso depois de 3 sinais consistentes seguidos pro mesmo
    artista (log bruto de todo evento em `eventos_escuta.json`, mesmo sem
    ajustar nada). 👎 forte também invalida do pool candidatos do mesmo
    artista ainda não consumidos (`pool.invalidar_relacionados`).
  - **Diversidade de sessão** - `recomendador.calcular_score`/`pool.
    consumir_proxima` ganharam `penalidades_sessao` (penaliza artista/gênero
    repetido demais NUMA sessão, sem esperar o dedup exato de faixa).
  - **`/perfil/aprovados`/`/perfil/desaprovados`** (novo) e
    `/radar/feedback_passivo` (novo) - expõem as listas curadas e o sinal
    fraco pro ERIS. 79 testes automatizados no total, todos passando.
- **"Musicas sem voto não saem do pool" (2026-08-26, pedido do usuário)** -
  `pool.consumir_proxima` não remove mais a faixa do pool ao tocar (só
  registra em `historico`, sem voto) - tocar sem avaliar não é sinal de
  rejeição nem de aprovação. Só sai do pool quem recebe um VOTO de verdade:
  `historico.foi_votada` (novo, substitui `foi_apresentada_alguma_vez`) e
  `pool.remover_track` (novo, chamado por `feedback.py` em toda avaliação
  explícita - remove só a faixa exata; `invalidar_relacionados` continua
  removendo o artista inteiro num 👎). 85 testes automatizados no total,
  todos passando.
- **`GET /perfil/voto`** (2026-08-27, pedido do usuário) - `historico.
  obter_voto` devolve `"positivo"`/`"negativo"`/`null` pra uma faixa - o
  ERIS usa isso pra mostrar "(👍)"/"(👎)" na mensagem de "tocando agora"
  quando ela já foi avaliada antes por quem iniciou a sessão. 87 testes
  automatizados no total, todos passando.

### Alterado
- **Um 👎 numa faixa não bloqueia mais o artista inteiro (2026-08-27)** -
  pedido do usuário: "um 👎 em 1 musica n pode condenar todas desse
  artista. Assim como o like n aprova todas tbm, algumas eu gosto e
  outras nao". `historico.artista_tem_feedback_negativo` (excluía o
  artista do ranking pra sempre) e `pool.invalidar_relacionados` (removia
  o artista inteiro do pool) foram REMOVIDOS - todo voto (👍/👎) agora
  fica estritamente na faixa exata (`pool.remover_track`). O único jeito
  de rejeitar um artista inteiro continua sendo a ação explícita
  `perfil.adicionar_artista_rejeitado` (`disliked_artists`), nunca
  inferido de uma avaliação de uma única música.

### Correções
- **`/caos` repetia a mesma música em sessões diferentes, com o pool
  vazio (2026-08-27)** - confirmado em produção: 3 chamadas separadas de
  `/caos` devolveram "Counting Stars - OneRepublic" toda vez. Causa raiz:
  pool ainda com 0 candidatos (nunca gerado desde a migração), camada 2
  (aprovadas) sempre devolvia a PRIMEIRA entrada não excluída - e como
  cada `/caos` é sessão nova, sempre a mesma. `continuacao.
  _aprovada_aleatoria_nao_excluida` agora sorteia entre todas as
  elegíveis. Ver `ARQUITETURA.md`.
- **`/caos` sempre devolvia a MESMA faixa mesmo com o pool cheio
  (2026-08-27)** - confirmado gerando o pool real do dono ao vivo (162
  candidatos) e chamando `/radar/semente` 6x seguidas: sempre "Duvet - bôa"
  (a de maior afinidade). Causa raiz: `pool.consumir_proxima` parou de
  remover a faixa escolhida do pool (mudança acima, "sem voto não sai") -
  `max()` estrito virou determinístico demais pra sessões novas (exclusão
  vazia). Corrigido: sorteia entre as top 5 por score em vez de sempre a
  melhor. Validado ao vivo depois da correção: 3 faixas diferentes em 6
  chamadas.
- **`/radar/semente` demorando ~10s pra responder** (2026-08-26, "Caos esta
  demorando para iniciar") - usava os mesmos limites do Radar semanal (até
  16 chamadas sequenciais ao provedor), mas bloqueia uma interação AO VIVO
  do Discord. Reduzido só nessa rota (`_coletar_candidatos` ganhou
  `max_artistas`/`max_generos`) - de ~9.8s pra ~4.5s medido, sem afetar o
  Radar semanal (roda em background, mantém os limites originais).
- **`obter_faixas_por_tag` sempre devolveu lista vazia** (2026-08-26,
  achado investigando "usei /caos... ela tocou apenas 1 musica, n mandou
  mais") - lia a chave errada da resposta do Last.fm (`toptracks` em vez
  de `tracks`, cada endpoint usa um wrapper diferente apesar do nome
  parecido). Bug existia desde que o método foi escrito - toda sugestão
  "por gênero" (descoberta/exploração, e o fallback quando o artista-
  semente está bloqueado por feedback negativo) nunca teve candidato
  nenhum vindo daqui. Corrigido, teste novo trava a chave certa (43
  testes no total).
