<p align="center">
  <img src="assets/icone_echo.png" alt="Project ECHO" width="180">
</p>

# Project ECHO

Serviço de recomendação musical que mantém um perfil de gosto, prepara o Radar Musical e escolhe sugestões sem repetir faixas recentes.

## Recursos principais

- perfil musical separado por pessoa;
- importação opcional do histórico do Last.fm;
- Radar Musical semanal;
- recomendações com base em artistas, gêneros e avaliações;
- controle de repetição por histórico e por sessão;
- fila pessoal preparada com antecedência.

O ECHO trabalha com dados e escolhas musicais. Ele não reproduz áudio e não tem interface gráfica.

## Origem do nome

ECHO vem de Eco, a ninfa da mitologia grega amaldiçoada por Hera a repetir apenas as últimas palavras que ouvia. Essa origem combina com o projeto, que ouve o que você gosta e traz de volta algo relacionado. Esse retorno aparece no Caos, nas recomendações, no Em Alta, nas Redescobertas e em novas descobertas.

### Identidade visual

A logo mostra uma figura feminina de perfil usando fones, com os olhos fechados e cercada por uma forma circular prateada. As barras ao fundo lembram um equalizador ou espectro de áudio e deixam clara a ideia de escuta e interpretação musical.

O cabelo e o círculo criam um fluxo que retorna sobre si mesmo. A figura representa a ninfa Eco adaptada ao domínio musical moderno: **ouvir → interpretar → devolver**.

## Requisitos

- Python 3.11 ou mais recente;
- chave gratuita do Last.fm para buscar músicas e lançamentos.

## Instalação e uso

```powershell
uv venv
uv pip install -e .
Copy-Item .env.example .env
python -m echo.main
```

Preencha `LASTFM_API_KEY` no `.env`. Sem a chave, o serviço abre e informa que o provedor está desativado, mas o Radar fica vazio. A API local usa a porta `8774`.

Para rodar sem terminal visível, use `iniciar_echo_oculto.vbs`.

Para executar os testes:

```powershell
uv pip install -e ".[dev]"
pytest
```

## Integrações com outros projetos

- **GAIA:** agenda a criação do Radar e apresenta as recomendações em conversa.
- **ERIS:** envia o que está tocando em uma chamada e usa a próxima sugestão do ECHO.
- **SIREN:** transforma as escolhas do ECHO em música tocando no desktop e acrescenta biblioteca, favoritos e playlists.

> **SIREN canta o que você quer ouvir.**\
> **ECHO ouve o que você gosta e traz de volta algo que combina com você.**

O ECHO também pode ser consultado diretamente pela API local.

## Documentação

- [Arquitetura](docs/ARQUITETURA.md)
- [Plano do player leve](docs/PLANO_ECHO_PLAYER_LEVE.md)
- [Pendências](docs/TODO.md)
- [Histórico de versões](CHANGELOG.md)
- [Padrão de documentação](docs/PADRAO_DOCUMENTACAO.md)

## Situação atual

O perfil musical, o Radar, o histórico, as avaliações e as sugestões para sessões ao vivo estão funcionando. As próximas etapas ficam em `docs/TODO.md`.
