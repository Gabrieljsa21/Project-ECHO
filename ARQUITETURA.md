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
própria (Spotify) que não precisa de credencial/lógica misturada ao processo
principal. O que FICA do lado da GAIA é justamente o que precisa da persona:
explicabilidade em linguagem natural (seção 13), apresentação do Radar (seção 7.4),
interpretação de feedback em linguagem natural, e o Agendador Diário decidindo a
cadência semanal.

## Separação de responsabilidades (`echo/core/`)

- **`perfil.py`** - gerencia preferências e pesos (`data/perfil.json`). Cadastro é
  manual nesta fase (artistas/gêneros favoritos e rejeitados, nível de descoberta) -
  sem histórico de reprodução real ainda (Fase 2).
- **`recomendador.py`** - calcula candidatos e ranking. Score determinístico:
  `compatibilidade*0.50 + relevância*0.25 + descoberta*0.15 + exploração*0.10`
  (seção 6/19 do ECHO_SPEC), com exclusão total (score negativo) pra repetição
  recente e artista rejeitado/com feedback negativo.
- **`radar.py`** - gera a seleção semanal: aplica a composição padrão (5
  compatibilidade / 3 relevância / 2 descoberta / 1 exploração pra 10 músicas, seção
  7.3) com diversidade (máx. 1 faixa por artista) e um preenchimento em RODÍZIO entre
  categorias quando alguma fica sem candidato suficiente - nunca um top-up genérico
  por score puro, que deixaria a categoria de maior peso (compatibilidade) engolir
  sozinha toda folga das demais.
- **`feedback.py`** - processa 👍/👎: ajuste pequeno e incremental de peso de gênero
  (nunca substitui o perfil, seção 21), delegado pra `perfil.ajustar_peso_genero`.
- **`historico.py`** - evita repetição (seção 8) e registra feedback; redescoberta
  permitida só após `DIAS_REDESCOBERTA` (90 dias, seção 9).

## Provedor musical (`echo/providers/`)

Abstração (`ProvedorMusical`) desacoplada do Spotify de propósito (seção 17/princípio
7 da seção 31 - "o núcleo do Modo DJ deve sobreviver à troca da integração
musical"). Métodos: `buscar_faixa`, `obter_lancamentos_novos`,
`obter_faixas_em_alta`, `obter_reproduzidas_recentemente`,
`obter_top_faixas_usuario`, `obter_top_artistas_usuario`, `criar_playlist`,
`adicionar_faixa_playlist`, `tocar_faixa`.

`ProvedorSpotify` (`providers/spotify.py`) implementa só o que a Fase 1 precisa via
fluxo **Client Credentials** (sem login de usuário, só dado público): busca de
faixas e lançamentos, com gênero resolvido por artista (a Spotify só expõe gênero
nesse nível, nunca em álbum/faixa). Os métodos que exigem autorização de USUÁRIO
(histórico real de reprodução, top faixas/artistas, playlists) levantam
`ProvedorIndisponivel` com mensagem clara - pertencem à Fase 2/3 (OAuth Authorization
Code, fora do escopo desta extração).

`ProvedorIndisponivel` é a única forma de falha esperada - nunca vira dado
inventado (seção 27: "nunca inventar músicas, artistas, datas ou métricas quando o
provedor não retornar informação confiável"). Sem credencial configurada, `GET
/status` já reporta isso antes de qualquer tentativa de Radar.

## Contrato HTTP (porta 8774, `echo/api_bridge.py`)

- `GET /status` - `{"provedor_configurado": bool}`.
- `GET /perfil` - perfil musical completo.
- `POST /perfil/artista_favorito` `{"nome", "genero"}` - também remove de
  rejeitados se estava lá.
- `POST /perfil/artista_rejeitado` `{"nome"}`.
- `POST /perfil/genero` `{"nome", "peso"}` - define (não ajusta) o peso de um
  gênero.
- `POST /perfil/discovery_level` `{"valor"}` (0.0-1.0).
- `GET /radar/atual?forcar=0|1` - devolve o último Radar já gerado hoje (a menos que
  `forcar=1`); gera um novo coletando lançamentos + busca pelos artistas favoritos.
  503 com `{"erro", "radar": []}` se o provedor não estiver disponível.
- `GET /radar/historico?limite=N` - últimas N recomendações (mais recente primeiro).
- `POST /radar/feedback` `{"track_id", "feedback", "genero"}` - `feedback` é
  `"positivo"` ou `"negativo"`; `genero` vem de quem está mandando (a GAIA reenvia o
  que recebeu junto com a faixa no Radar).

## Persistência (`data/`, gitignored)

`perfil.json`, `historico_recomendacoes.json`, `radar_estado.json` - lidos do disco a
cada chamada (nunca cacheados em memória entre requests), mesmo padrão já usado no
HESTIA/MOIRAI depois do bug real de cache stale documentado lá
(`Project G.A.I.A/assistant/docs/CORRECOES.md`).

## O que fica pendente pra Fase 2/3 (ver `TODO.md`)

Histórico real de reprodução, peso comportamental, OAuth de usuário (playlists,
top faixas/artistas, "em alta" via provedor), Playlist Descobertas automática, Em
Alta, Redescobertas dedicadas, nível de descoberta configurável de verdade
(hoje só persiste o valor, não influencia o ranking ainda), recomendações
contextuais, múltiplos provedores musicais.

## Integração com a GAIA (a fazer no repo dela)

`integrations/echo_client.py` (mesmo padrão de `hestia_client.py`) + uma tag sob
demanda (ex.: `<RADAR_MUSICAL>`) pra o usuário poder pedir o Radar em conversa -
cadência proativa semanal (Agendador Diário) fica como próximo passo depois de
validar a busca/ranking com uma credencial Spotify real.
