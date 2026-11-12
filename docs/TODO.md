# TODO - Project ECHO

Fase 1 do MVP **completa** (2026-08-25): perfil musical, ranking determinístico,
Radar Musical sob demanda E proativo (semanal, via Agendador Diário da GAIA),
histórico/dedup, feedback 👍/👎, validado contra a API real do Last.fm com
credencial real do usuário. Ver `CHANGELOG.md` pro detalhe completo.

## Prioridade média (Fase 2 do ECHO_SPEC)

- **Consumir `/em_alta` e `/redescobertas` em conversa na GAIA** - o SIREN já mostra as duas listas. Falta o `echo_client.py` da GAIA ter as chamadas e alguma tag ou comando expor isso em conversa. Complexidade: baixa (chamadas) a média (desenho de tag e persona). Status: não iniciado.

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
