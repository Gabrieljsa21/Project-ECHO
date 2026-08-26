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
própria (provedor musical) que não precisa de credencial/lógica misturada ao
processo principal. O que FICA do lado da GAIA é justamente o que precisa da persona:
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

Abstração (`ProvedorMusical`) desacoplada de propósito (seção 17/princípio 7 da
seção 31 - "o núcleo do Modo DJ deve sobreviver à troca da integração musical").
Métodos: `buscar_faixa`, `obter_faixas_do_artista`, `obter_faixas_por_tag`,
`obter_lancamentos_novos`, `obter_faixas_em_alta`, `obter_reproduzidas_recentemente`,
`obter_top_faixas_usuario`, `obter_top_artistas_usuario`, `criar_playlist`,
`adicionar_faixa_playlist`, `tocar_faixa`.

### Por que Last.fm (não Spotify) - decisão de 2026-08-25

A implementação de referência original usou o Spotify (Client Credentials, sem
login), mas uma mudança de política da própria Spotify em fevereiro/março de 2026
(1) passou a exigir **assinatura Premium ATIVA** só pra manter o app de
desenvolvedor funcionando (se o Premium expirar, o app para) e (2) **removeu o
endpoint de "novos lançamentos"** (`GET /browse/new-releases`) sem substituto
oficial, junto com a busca em lote de artistas. Isso quebrava justamente a
"busca de lançamentos" da Fase 1, e criava um vínculo de pagamento recorrente
indesejado pra um projeto pessoal.

`ProvedorLastfm` (`providers/lastfm.py`) substituiu o Spotify: API gratuita, sem
assinatura, sem login de usuário, chave gerada em 2 minutos. Como a Fase 1 nunca
toca música de verdade (isso só entra na Fase 3, com login de usuário num
serviço de streaming), o Last.fm - que é puramente um serviço de
metadado/scrobbling - encaixa melhor que o Spotify já encaixava:
- `chart.gettoptracks` (chart global) alimenta `obter_lancamentos_novos` -
  aproximação honesta de "relevância atual" (Last.fm não tem conceito de data de
  lançamento, só de popularidade de reprodução).
- `artist.gettoptracks` alimenta `obter_faixas_do_artista` - substitui o hack
  `buscar_faixa('artist:"X"')` que a versão Spotify precisava, com um endpoint
  dedicado de verdade.
- `tag.gettoptracks` alimenta `obter_faixas_por_tag` (NOVO, não existia na
  versão Spotify) - candidato dedicado por gênero preferido, alimentando
  descoberta/exploração melhor do que só sobras do chart global.
- Popularidade normalizada em escala LOGARÍTMICA de `listeners` (contagem bruta,
  sem teto) pra 0-100, já que o Last.fm não tem um score de popularidade oficial
  como o Spotify tinha - aproximação documentada em `lastfm.py`.

Métodos que exigem histórico de USUÁRIO (top faixas/artistas, reproduzidas
recentemente - Fase 2, precisaria de um username do Last.fm vinculado) e
playlist/playback (Fase 3 - Last.fm não faz streaming, vai exigir um provedor
DIFERENTE, ex.: Spotify com OAuth de usuário de verdade) levantam
`ProvedorIndisponivel` com mensagem clara.

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
  `forcar=1`); gera um novo coletando chart global + faixas dos artistas favoritos +
  faixas por gênero preferido. 503 com `{"erro", "radar": []}` se o provedor não
  estiver disponível.
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

Histórico real de reprodução, peso comportamental (username do Last.fm
vinculado), Playlist Descobertas automática (precisa de um provedor com
streaming - Last.fm não faz), Em Alta dedicado, Redescobertas dedicadas, nível
de descoberta configurável de verdade (hoje só persiste o valor, não influencia
o ranking ainda), recomendações contextuais, playback/playlist de verdade
(exige um segundo provedor com OAuth de usuário, ex.: Spotify).

## Integração com a GAIA (feita no repo dela)

`integrations/echo_client.py` (mesmo padrão de `hestia_client.py`) + tag
`<RADAR_MUSICAL>` (`core/tools/handlers.py`) pra o usuário poder pedir o Radar em
conversa, mais `garantir_echo_rodando()` subindo o processo automaticamente no
boot da GAIA (`integrations/iris_bridge.py`, mesmo padrão do ERIS). Cadência
proativa semanal (Agendador Diário) ainda fica como próximo passo - hoje o Radar
só é GERADO sob demanda.
