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

### Pendências conhecidas
- Nunca testado contra a API real do Last.fm (só candidatos sintéticos nos testes) -
  precisa de `LASTFM_API_KEY` real (gratuita, ver `.env.example`).
- Cadência proativa semanal via Agendador Diário ainda não wireada - Radar só é
  GERADO sob demanda (o processo já fica de pé sozinho, isso está resolvido).
