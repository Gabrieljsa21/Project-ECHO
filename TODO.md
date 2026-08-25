# TODO - Project ECHO

## Prioridade alta

- **Integração do lado da GAIA** (`integrations/echo_client.py`, mesmo padrão de
  `hestia_client.py`) - Complexidade: baixa. Status: não iniciado. Sem isso, o ECHO
  existe mas ninguém chama.
- **Tag sob demanda `<RADAR_MUSICAL>`** (`core/tools/handlers.py`/`core/agent/
  turno.py`, mesmo padrão de `<LANCAMENTOS>`) - Complexidade: baixa. Status: não
  iniciado.
- **Validar contra a Web API real do Spotify** (criar app em
  developer.spotify.com/dashboard, testar `buscar_faixa`/`obter_lancamentos_novos`
  com dados reais) - Complexidade: baixa, mas bloqueada por credencial que só o
  usuário pode gerar. Status: não iniciado.

## Prioridade média (Fase 2 do ECHO_SPEC)

- **Cadência proativa semanal via Agendador Diário da GAIA** (hoje o Radar só é
  gerado sob demanda via `GET /radar/atual`) - Complexidade: média (depende da
  integração acima existir primeiro). Status: não iniciado.
- **Histórico real de reprodução + peso comportamental** (seção 5.2 do ECHO_SPEC -
  `obter_reproduzidas_recentemente`/`obter_top_faixas_usuario`/
  `obter_top_artistas_usuario`) - requer OAuth Authorization Code do Spotify (login
  de usuário), não só Client Credentials. Complexidade: alta. Status: não iniciado.
- **Nível de descoberta influenciando o ranking de verdade** (hoje
  `discovery_level` só persiste no perfil, `core/recomendador.py` ainda não lê esse
  valor pra alterar os pesos) - Complexidade: baixa. Status: não iniciado.
- **Redescobertas dedicadas** (seção 9 - recuperar música que o usuário gostava mas
  não ouve há tempo, distinto de "evitar repetição") - Complexidade: média. Status:
  não iniciado.
- **Em Alta** (seção 3.3, separado do Radar Musical semanal) - Complexidade: baixa
  (reaproveita `obter_faixas_em_alta`, que ainda não tem implementação real no
  provedor Spotify - ver Fase 3). Status: não iniciado.
- **Playlist "Descobertas da GAIA" automática** (seção 11) - requer
  `criar_playlist`/`adicionar_faixa_playlist` com OAuth de usuário. Complexidade:
  média. Status: não iniciado.

## Prioridade baixa (Fase 3 do ECHO_SPEC)

- **Recomendações contextuais** (seção 10) - Complexidade: alta (depende de sinal de
  contexto que a GAIA não expõe hoje). Status: não iniciado.
- **Múltiplos provedores musicais** (YouTube Music, etc., além do Spotify) -
  Complexidade: alta. Status: não iniciado.
- **`obter_faixas_em_alta` real** - Spotify não expõe um endpoint público de "em
  alta" via Client Credentials; precisaria de OAuth de usuário ou provedor
  diferente. Complexidade: média. Status: bloqueado (ver decisão em
  `providers/spotify.py`).

## Bloqueado por decisão/insumo do usuário

- Credencial real do Spotify (`SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET`) - sem
  isso, nada do provedor pode ser validado contra dado real.
