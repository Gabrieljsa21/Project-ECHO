# TODO - Project ECHO

Fase 1 do MVP **completa** (2026-08-25): perfil musical, ranking determinístico,
Radar Musical sob demanda E proativo (semanal, via Agendador Diário da GAIA),
histórico/dedup, feedback 👍/👎, validado contra a API real do Last.fm com
credencial real do usuário. Ver `CHANGELOG.md` pro detalhe completo.

## Prioridade média (Fase 2 do ECHO_SPEC)

- **Consumir `/em_alta` e `/redescobertas` do lado da GAIA** - os endpoints já
  existem no ECHO (`core/em_alta.py`, `core/redescobertas.py`, ver
  `ARQUITETURA.md`), mas `echo_client.py` (repo da GAIA) ainda não tem
  wrappers pra eles, e nenhuma tag/comando os expõe em conversa - mesmo padrão
  de outros endpoints já expostos "pra um Painel futuro". Complexidade: baixa
  (wrapper) a média (desenho de tag/persona). Status: não iniciado.

## Prioridade baixa (Fase 3 do ECHO_SPEC)

- **Playlist "Descobertas da GAIA" automática** (seção 11 - SALVAR uma
  playlist gerenciada, diferente do playback ao vivo, que já funciona via
  ERIS/YouTube - ver `ARQUITETURA.md`) - precisa de um provedor com
  biblioteca/playlist de usuário de verdade (ex.: Spotify com OAuth
  Authorization Code, se a instabilidade de política dele se resolver).
  Complexidade: alta. Status: não iniciado.
- **Recomendações contextuais** (seção 10) - Complexidade: alta (depende de sinal de
  contexto que a GAIA não expõe hoje). Status: não iniciado.
- **Múltiplos provedores musicais** (rodar Last.fm + Spotify/YouTube Music juntos,
  por exemplo) - Complexidade: alta. Status: não iniciado.
