<p align="center">
  <img src="https://img.shields.io/badge/fase-1%20MVP-blue" alt="Fase 1 MVP">
</p>

# Project ECHO

Modo DJ da GAIA - perfil musical persistente, ranking determinístico, Radar Musical
semanal e continuação ao vivo pra quem toca música de verdade numa call
([Project ERIS](../../Project-ERIS)). Processo próprio, **sem interface gráfica** -
só uma ponte HTTP; quem decide QUANDO gerar o Radar (Agendador Diário ou comando do
usuário) e COMO apresentar (persona, explicação da recomendação) é sempre a
[GAIA](../Project%20G.A.I.A) (assistente pessoal do mesmo autor), consultando o
ECHO por HTTP. O ECHO nunca toca áudio nem sabe o que é YouTube/Discord - só
metadado/ranking.

Baseado na especificação completa em `Project G.A.I.A/Project ECHO.md` (32 seções -
objetivo, perfil musical, motor de recomendação, Radar Musical, feedback,
explicabilidade, MVP faseado). Esta Fase 1 implementa o essencial determinístico do
motor; a explicabilidade em linguagem natural e a apresentação ao usuário continuam
do lado da GAIA (mesmo padrão de extração do HESTIA/MOIRAI - satélite fica com o
dado/ranking, GAIA fica com a persona).

## A origem do nome

Eco - o Modo DJ devolve ao usuário uma versão nova/atual do que ele já gosta, sem
nunca deixar de ser reconhecível; também referência às "bolhas" musicais que o motor
deliberadamente evita (seção 6.4 - Exploração).

## Escopo desta Fase 1 (MVP)

- [x] Estrutura do Modo DJ (`echo/core/`, `echo/providers/`)
- [x] Perfil musical persistente (`data/perfil.json`)
- [x] Cadastro manual de artistas/gêneros favoritos (um por um, ou em LOTE
      colando uma playlist/lista - ver `<CADASTRAR_ARTISTAS>` no repo da GAIA)
- [x] Importação de histórico real de escuta via Last.fm/scrobbling (opcional,
      requer `LASTFM_USERNAME` vinculado - ver `<IMPORTAR_GOSTO_MUSICAL>`)
- [x] Busca de lançamentos (Last.fm - chart global + gênero, sem login/assinatura)
- [x] Radar Musical semanal (geração sob demanda - cadência real fica com o
      Agendador Diário da GAIA)
- [x] Histórico de recomendações + dedup (redescoberta só após 90 dias)
- [x] 👍 / 👎 (ajusta peso de gênero incrementalmente, nunca substitui o perfil)
- [x] Evitar duplicatas / máx. 1 faixa por artista por edição
- [x] Continuação ao vivo (`POST /radar/proxima`) - uma sugestão por vez,
      semeada pela faixa que está tocando agora numa call real (Modo Música
      do ERIS), com dedup de sessão

Fase 2 (peso comportamental contínuo, Em Alta, Redescobertas, nível de
descoberta configurável) e Fase 3 (playlists gerenciadas, múltiplos
provedores) ficam para depois - ver `TODO.md`.

## Uso standalone

```bash
uv venv
uv pip install -e .
python -m echo.main
```

Sem `LASTFM_API_KEY` (ver `.env.example` - chave grátis, sem cartão, gerada em
last.fm/api/account/create), o ECHO sobe normalmente mas `GET /status` reporta
`provedor_configurado: false` e o Radar fica vazio - nunca inventa lançamento/
música pra preencher (seção 27 do ECHO_SPEC).

Sem loop de manutenção próprio (mesmo padrão do HESTIA) - o ECHO fica parado
esperando requisição HTTP na porta 8774 (`echo/api_bridge.py`). A geração do Radar só
roda quando alguém pergunta (normalmente a GAIA).

## Rodar os testes

```bash
uv pip install -e ".[dev]"
pytest
```

## Integração com a GAIA

`integrations/echo_client.py` (repo da GAIA) fala com a ponte HTTP daqui, e
`garantir_echo_rodando()` sobe o processo automaticamente no boot dela (mesmo
padrão de ERIS/HESTIA/MOIRAI) - não precisa rodar `python -m echo.main` na mão.
Ver `ARQUITETURA.md` pro contrato HTTP completo e as decisões de design
(provedor desacoplado, por que Last.fm em vez de Spotify, ranking sem LLM,
diversidade/dedup).
