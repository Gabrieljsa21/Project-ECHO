# TODO - Project ECHO

Fase 1 do MVP **completa** (2026-08-25): perfil musical, ranking determinístico,
Radar Musical sob demanda E proativo (semanal, via Agendador Diário da GAIA),
histórico/dedup, feedback 👍/👎, validado contra a API real do Last.fm com
credencial real do usuário. Ver `CHANGELOG.md` pro detalhe completo.

## Prioridade média (Fase 2 do ECHO_SPEC)

- **Histórico real de reprodução + peso comportamental** (seção 5.2 do ECHO_SPEC
  - `obter_reproduzidas_recentemente`/`obter_top_faixas_usuario`/
  `obter_top_artistas_usuario`) - requer um USERNAME do Last.fm vinculado (não
  precisa de OAuth completo, mas é dado de outra pessoa/conta, fora do escopo
  desta Fase 1). Complexidade: média. Status: não iniciado.
- **Nível de descoberta influenciando o ranking de verdade** (hoje
  `discovery_level` só persiste no perfil, `core/recomendador.py` ainda não lê esse
  valor pra alterar os pesos) - Complexidade: baixa. Status: não iniciado.
- **Redescobertas dedicadas** (seção 9 - recuperar música que o usuário gostava mas
  não ouve há tempo, distinto de "evitar repetição") - Complexidade: média. Status:
  não iniciado.
- **Em Alta** (seção 3.3, separado do Radar Musical semanal) - Complexidade: baixa
  (reaproveita a mesma fonte de `obter_lancamentos_novos`, já que
  `obter_faixas_em_alta` do provedor Last.fm não tem uma fonte distinta - ver
  `providers/lastfm.py`). Status: não iniciado.

## Prioridade baixa (Fase 3 do ECHO_SPEC)

- **Playback/playlist de verdade** (`criar_playlist`/`adicionar_faixa_playlist`/
  `tocar_faixa`) - Last.fm não faz streaming, precisa de um SEGUNDO provedor
  com OAuth Authorization Code de usuário de verdade (ex.: Spotify, se a
  instabilidade de política dele se resolver, ou outro serviço). Complexidade:
  alta. Status: não iniciado.
- **Playlist "Descobertas da GAIA" automática** (seção 11) - depende do item
  acima (precisa de playback/playlist real). Complexidade: média. Status: não
  iniciado.
- **Recomendações contextuais** (seção 10) - Complexidade: alta (depende de sinal de
  contexto que a GAIA não expõe hoje). Status: não iniciado.
- **Múltiplos provedores musicais** (rodar Last.fm + Spotify/YouTube Music juntos,
  por exemplo) - Complexidade: alta. Status: não iniciado.
