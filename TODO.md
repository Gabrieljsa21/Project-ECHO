# TODO - Project ECHO

Fase 1 do MVP **completa** (2026-08-25): perfil musical, ranking determinístico,
Radar Musical sob demanda E proativo (semanal, via Agendador Diário da GAIA),
histórico/dedup, feedback 👍/👎, validado contra a API real do Last.fm com
credencial real do usuário. Ver `CHANGELOG.md` pro detalhe completo.

## Pendências conhecidas

- **Log em disco quando rodando escondido (2026-09-01)** - `iniciar_echo_
  oculto.vbs` (novo) sobe o processo via `pythonw.exe`, que descarta
  `print()`/traceback no vazio (sem console nenhum) - sem um
  `_RedirecionadorLog` (mesmo padrão de `Project-ERIS/eris/main.py`), um
  crash silencioso não deixa nenhum rastro. Não bloqueou a criação do
  launcher, mas dificulta diagnosticar qualquer problema rodando assim.

## Prioridade média (Fase 2 do ECHO_SPEC)

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

- **Playback de verdade - RESOLVIDO por outro caminho (2026-08-25)**: o
  Modo Música do [Project ERIS](../../Project-ERIS) já toca música de
  verdade numa call (YouTube via `yt-dlp`) consultando o ECHO só pra
  "qual é a próxima" (`POST /radar/proxima`) - nunca precisou de
  `criar_playlist`/`adicionar_faixa_playlist`/`tocar_faixa` na abstração de
  provedor do ECHO, que continuam sem implementação (Last.fm não faz
  streaming, e o caminho real acabou não precisando de OAuth do Spotify).
- **Playlist "Descobertas da GAIA" automática** (seção 11 - SALVAR uma
  playlist gerenciada, diferente de "tocar" que já está resolvido acima) -
  precisa de um provedor com biblioteca/playlist de usuário de verdade
  (ex.: Spotify com OAuth Authorization Code, se a instabilidade de
  política dele se resolver). Complexidade: alta. Status: não iniciado.
- **Recomendações contextuais** (seção 10) - Complexidade: alta (depende de sinal de
  contexto que a GAIA não expõe hoje). Status: não iniciado.
- **Múltiplos provedores musicais** (rodar Last.fm + Spotify/YouTube Music juntos,
  por exemplo) - Complexidade: alta. Status: não iniciado.
