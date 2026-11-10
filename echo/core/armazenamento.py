# -*- coding: utf-8 -*-
"""Leitura e gravação dos arquivos JSON de `data/` (2026-11-09).

Antes cada módulo abria o arquivo com `open(..., "w")` e devolvia vazio
quando a leitura falhava. Uma queda no meio da gravação deixava o arquivo
cortado; a leitura seguinte devolvia vazio e a próxima gravação apagava
tudo (votos, pool, notas de artista), sem cópia nenhuma.

O que este módulo garante:

- gravação atômica: escreve num arquivo temporário e troca com
  `os.replace`; o arquivo de verdade nunca fica pela metade;
- `<arquivo>.bak` com o conteúdo de antes da última gravação;
- uma cópia por dia em `backups/` ao lado do arquivo, feita antes da
  primeira gravação do dia (ficam as `DIAS_DE_BACKUP` mais recentes);
- arquivo ilegível nunca é sobrescrito em silêncio: a leitura tenta o
  `.bak` e, se também falhar, guarda o arquivo como `.corrompido-<data>`
  antes de devolver o valor padrão;
- cache em memória opcional (`cache=True`), conferido pelo tamanho e pela
  data de modificação, para arquivo grande lido muitas vezes por pedido.

`LOCK` é a trava única de toda a persistência. Quem lê, altera e grava
segura a trava do começo ao fim. É reentrante: uma função com a trava pode
chamar outra que também a pede."""
import functools
import json
import os
import shutil
import threading
import time
from datetime import date, datetime

LOCK = threading.RLock()

DIAS_DE_BACKUP = 7
PASTA_BACKUPS = "backups"

_cache = {}  # caminho absoluto -> (assinatura, dados)
_versoes = {}  # caminho absoluto -> contador, sobe a cada leitura do disco ou gravação


def com_trava(funcao):
    """Decorador: a função inteira roda com `LOCK` (ler, alterar e gravar
    sem outra thread no meio)."""
    @functools.wraps(funcao)
    def envolvida(*args, **kwargs):
        with LOCK:
            return funcao(*args, **kwargs)
    return envolvida


def _abs(caminho):
    return os.path.abspath(caminho)


def _assinatura(caminho):
    info = os.stat(caminho)
    return (info.st_mtime_ns, info.st_size)


def _subir_versao(caminho_abs):
    _versoes[caminho_abs] = _versoes.get(caminho_abs, 0) + 1


def versao(caminho):
    """Muda sempre que o conteúdo em cache de `caminho` muda. Serve para
    quem monta um índice em cima dos dados saber quando refazê-lo."""
    return _versoes.get(_abs(caminho), 0)


def _ler_json(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _trocar(origem, destino):
    """`os.replace` com novas tentativas: no Windows a troca falha se outro
    processo (antivírus, indexador) estiver com o destino aberto."""
    for tentativa in range(5):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:
            if tentativa == 4:
                raise
            time.sleep(0.05 * (tentativa + 1))


def _recuperar(caminho, padrao):
    """`caminho` falta ou está ilegível. Tenta o `.bak`; sem ele, guarda o
    arquivo estragado e devolve o padrão."""
    reserva = caminho + ".bak"
    existe = os.path.exists(caminho)
    if os.path.exists(reserva):
        try:
            dados = _ler_json(reserva)
        except Exception:
            dados = None
        if dados is not None:
            if existe:
                _guardar_corrompido(caminho)
            shutil.copy2(reserva, caminho)
            print(f" [ECHO] {caminho} estava ilegível ou ausente; restaurado de {reserva}.")
            return dados
    if existe:
        _guardar_corrompido(caminho)
        print(f" [ECHO] {caminho} estava ilegível e não havia cópia boa; começando vazio.")
    return padrao()


def _guardar_corrompido(caminho):
    destino = f"{caminho}.corrompido-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        _trocar(caminho, destino)
        print(f" [ECHO] Arquivo ilegível guardado em {destino}.")
    except OSError as e:
        print(f" [ECHO] Não consegui guardar o arquivo ilegível {caminho}: {e}")


def carregar(caminho, padrao, cache=False):
    """Conteúdo de `caminho`, ou `padrao()` se ele não existir. Com
    `cache=True` devolve o mesmo objeto enquanto o arquivo não mudar: quem
    alterar esse objeto precisa chamar `salvar` em seguida."""
    caminho_abs = _abs(caminho)
    with LOCK:
        if cache:
            guardado = _cache.get(caminho_abs)
            if guardado is not None:
                try:
                    if _assinatura(caminho) == guardado[0]:
                        return guardado[1]
                except OSError:
                    pass
        if os.path.exists(caminho):
            try:
                dados = _ler_json(caminho)
            except Exception:
                dados = _recuperar(caminho, padrao)
        elif os.path.exists(caminho + ".bak"):
            dados = _recuperar(caminho, padrao)
        else:
            dados = padrao()
        if cache:
            try:
                _cache[caminho_abs] = (_assinatura(caminho), dados)
            except OSError:
                _cache.pop(caminho_abs, None)
            _subir_versao(caminho_abs)
        return dados


def _backup_diario(caminho):
    """Copia o arquivo atual para `backups/` antes da primeira gravação do
    dia e apaga as cópias além das `DIAS_DE_BACKUP` mais recentes."""
    pasta = os.path.join(os.path.dirname(caminho) or ".", PASTA_BACKUPS)
    nome, extensao = os.path.splitext(os.path.basename(caminho))
    destino = os.path.join(pasta, f"{nome}.{date.today().isoformat()}{extensao}")
    if os.path.exists(destino):
        return
    os.makedirs(pasta, exist_ok=True)
    shutil.copy2(caminho, destino)
    copias = sorted(
        f for f in os.listdir(pasta)
        if f.startswith(nome + ".") and f.endswith(extensao) and len(f) == len(nome) + len(extensao) + 11
    )
    for antiga in copias[:-DIAS_DE_BACKUP]:
        try:
            os.remove(os.path.join(pasta, antiga))
        except OSError:
            pass


def _serializar(dados):
    """Lista: um item por linha, sem recuo. `json.dump` com `indent` usa o
    codificador em Python puro e levava mais de 100 ms num histórico de
    1 MB, a cada sugestão; assim o codificador em C faz o trabalho e o
    arquivo continua legível linha a linha. Dicionário (arquivos pequenos)
    segue com recuo."""
    if isinstance(dados, list):
        if not dados:
            return "[]"
        return "[\n" + ",\n".join(json.dumps(item, ensure_ascii=False) for item in dados) + "\n]"
    return json.dumps(dados, ensure_ascii=False, indent=2)


def salvar(caminho, dados, cache=False):
    caminho_abs = _abs(caminho)
    with LOCK:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            f.write(_serializar(dados))
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(caminho):
            try:
                _backup_diario(caminho)
            except OSError as e:
                print(f" [ECHO] Backup diário de {caminho} falhou: {e}")
            try:
                _trocar(caminho, caminho + ".bak")
            except OSError as e:
                print(f" [ECHO] Não consegui atualizar {caminho}.bak: {e}")
        _trocar(temporario, caminho)
        if cache:
            _cache[caminho_abs] = (_assinatura(caminho), dados)
            _subir_versao(caminho_abs)
        else:
            _cache.pop(caminho_abs, None)
