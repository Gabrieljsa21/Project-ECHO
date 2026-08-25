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
  (`echo/providers/__init__.py`) com implementação de referência via Spotify Web API
  em fluxo Client Credentials (`echo/providers/spotify.py`). Ponte HTTP na porta
  8774 (`echo/api_bridge.py`), guarda de instância única na porta 8775
  (`echo/main.py`), sem loop de manutenção próprio (mesmo padrão do HESTIA - a GAIA
  decide quando gerar o Radar). 17 testes automatizados (`tests/`) cobrindo
  perfil/histórico/radar, todos passando.

### Pendências conhecidas
- Integração do lado da GAIA (`integrations/echo_client.py` + tag sob demanda) ainda
  não implementada - ver `TODO.md`.
- Só validado com candidatos sintéticos nos testes; nunca testado contra a Web API
  real do Spotify (precisa de `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` reais).
