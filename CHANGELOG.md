# Changelog

## [Unreleased]

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
