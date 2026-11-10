# -*- coding: utf-8 -*-
"""Persistência segura (2026-11-09): gravação atômica, `.bak`, backup diário,
arquivo ilegível preservado, histórico sem repetição sem voto e respostas de
erro da ponte HTTP."""
import io
import json
import os

from echo import api_bridge
from echo.core import armazenamento
from echo.core import historico as historico_mod
from echo.providers import ProvedorIndisponivel
from echo.providers import lastfm as lastfm_mod

USUARIO = "111111"


def test_salvar_e_carregar(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    assert armazenamento.carregar(arquivo, dict) == {}
    armazenamento.salvar(arquivo, {"a": 1})
    assert armazenamento.carregar(arquivo, dict) == {"a": 1}
    assert not os.path.exists(arquivo + ".tmp")


def test_segunda_gravacao_deixa_bak_com_o_conteudo_anterior(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    armazenamento.salvar(arquivo, {"versao": 1})
    armazenamento.salvar(arquivo, {"versao": 2})
    with open(arquivo + ".bak", encoding="utf-8") as f:
        assert json.load(f) == {"versao": 1}


def test_arquivo_cortado_e_restaurado_do_bak(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    armazenamento.salvar(arquivo, {"versao": 1})
    armazenamento.salvar(arquivo, {"versao": 2})
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write('{"versao": 2, "cort')

    assert armazenamento.carregar(arquivo, dict) == {"versao": 1}
    assert any(".corrompido-" in nome for nome in os.listdir(tmp_path))


def test_arquivo_ilegivel_sem_bak_e_guardado_e_nao_sobrescrito(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write("isso não é json")

    assert armazenamento.carregar(arquivo, list) == []
    guardados = [nome for nome in os.listdir(tmp_path) if ".corrompido-" in nome]
    assert len(guardados) == 1
    with open(tmp_path / guardados[0], encoding="utf-8") as f:
        assert f.read() == "isso não é json"


def test_arquivo_sumido_volta_do_bak(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    armazenamento.salvar(arquivo, {"versao": 1})
    armazenamento.salvar(arquivo, {"versao": 2})
    os.remove(arquivo)
    assert armazenamento.carregar(arquivo, dict) == {"versao": 1}


def test_backup_diario_guarda_o_conteudo_de_antes_da_primeira_gravacao_do_dia(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    armazenamento.salvar(arquivo, {"versao": 1})
    armazenamento.salvar(arquivo, {"versao": 2})
    armazenamento.salvar(arquivo, {"versao": 3})

    copias = os.listdir(tmp_path / "backups")
    assert len(copias) == 1
    with open(tmp_path / "backups" / copias[0], encoding="utf-8") as f:
        assert json.load(f) == {"versao": 1}


def test_backup_diario_mantem_so_os_mais_recentes(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    pasta = tmp_path / "backups"
    pasta.mkdir()
    for dia in range(1, 11):
        (pasta / f"dados.2026-01-{dia:02d}.json").write_text("{}", encoding="utf-8")
    armazenamento.salvar(arquivo, {"versao": 1})
    armazenamento.salvar(arquivo, {"versao": 2})

    copias = sorted(os.listdir(pasta))
    assert len(copias) == armazenamento.DIAS_DE_BACKUP
    assert "dados.2026-01-01.json" not in copias


def test_cache_devolve_o_mesmo_objeto_e_percebe_mudanca_externa(tmp_path):
    arquivo = str(tmp_path / "dados.json")
    armazenamento.salvar(arquivo, [1], cache=True)
    primeiro = armazenamento.carregar(arquivo, list, cache=True)
    assert armazenamento.carregar(arquivo, list, cache=True) is primeiro

    versao_antes = armazenamento.versao(arquivo)
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump([1, 2, 3], f)
    assert armazenamento.carregar(arquivo, list, cache=True) == [1, 2, 3]
    assert armazenamento.versao(arquivo) > versao_antes


# ------------------------------------------------------------------ histórico

def test_faixa_sem_voto_que_toca_de_novo_nao_cria_linha_nova():
    for _ in range(4):
        historico_mod.registrar_recomendacao(USUARIO, "Duvet", "bôa", reason="pool", category=None)
    historico_mod.registrar_recomendacao(USUARIO, "Outra", "Banda", reason="pool", category=None)
    historico_mod.registrar_recomendacao(USUARIO, "Duvet", "bôa", reason="pool", category=None)

    historico = historico_mod.carregar_historico()
    assert len(historico) == 2
    assert historico[-1]["titulo"] == "Duvet"  # a mais recente vai para o fim
    assert historico[-1]["aparicoes"] == 5


def test_entrada_com_voto_nao_e_alterada_por_nova_aparicao():
    historico_mod.registrar_recomendacao(USUARIO, "Duvet", "bôa", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Duvet", "bôa"), "positivo")
    historico_mod.registrar_recomendacao(USUARIO, "Duvet", "bôa", reason="pool", category=None)
    historico_mod.registrar_recomendacao(USUARIO, "Duvet", "bôa", reason="pool", category=None)

    historico = historico_mod.carregar_historico()
    assert [e.get("user_feedback") for e in historico] == ["positivo", None]
    assert historico_mod.obter_voto(USUARIO, "Duvet", "bôa") == "positivo"


def _entrada(titulo, voto=None, usuario=USUARIO, dia="2026-09-01"):
    return {
        "discord_user_id": usuario, "track_id": historico_mod.track_id(titulo, "Banda"), "titulo": titulo,
        "artista": "Banda", "recommended_at": dia, "reason": "pool", "category": None,
        "user_feedback": voto, "subsequent_play_count": 0,
    }


def test_compactar_une_repeticoes_e_preserva_votos(tmp_path):
    historico_mod._salvar_historico([
        _entrada("A", dia="2026-09-01"),
        _entrada("A", voto="positivo", dia="2026-09-02"),
        _entrada("A", dia="2026-09-03"),
        _entrada("A", dia="2026-09-04"),
        _entrada("B", dia="2026-09-01"),
        _entrada("B", dia="2026-09-05"),
        _entrada("B", dia="2026-09-06", usuario="222222"),
        _entrada("C", voto="negativo", dia="2026-09-07"),
    ])
    aprovadas_antes = historico_mod.obter_aprovadas(USUARIO)
    ultima_antes = historico_mod.obter_ultima_aparicao(USUARIO, historico_mod.track_id("A", "Banda"))

    assert historico_mod.compactar() == 3

    historico = historico_mod.carregar_historico()
    assert [(e["titulo"], e["user_feedback"], e["discord_user_id"]) for e in historico] == [
        ("A", "positivo", USUARIO), ("A", None, USUARIO), ("B", None, USUARIO),
        ("B", None, "222222"), ("C", "negativo", USUARIO),
    ]
    assert historico[1]["aparicoes"] == 4
    assert historico_mod.obter_aprovadas(USUARIO) == aprovadas_antes
    assert historico_mod.obter_ultima_aparicao(USUARIO, historico_mod.track_id("A", "Banda")) == ultima_antes
    assert historico_mod.obter_voto(USUARIO, "C", "Banda") == "negativo"
    assert any(".antes-compactacao-" in nome for nome in os.listdir(tmp_path))
    assert historico_mod.compactar() == 0


def test_consultas_enxergam_gravacao_feita_logo_antes():
    """O índice em memória é refeito a cada gravação."""
    assert not historico_mod.foi_recomendada_recentemente(USUARIO, "A", "Banda")
    historico_mod.registrar_recomendacao(USUARIO, "A", "Banda", reason="pool", category=None)
    assert historico_mod.foi_recomendada_recentemente(USUARIO, "A", "Banda")
    assert not historico_mod.foi_votada(USUARIO, "A", "Banda")
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("A", "Banda"), "negativo")
    assert historico_mod.foi_votada(USUARIO, "A", "Banda")
    historico_mod.limpar_feedback(USUARIO, historico_mod.track_id("A", "Banda"))
    assert not historico_mod.foi_votada(USUARIO, "A", "Banda")


# ------------------------------------------------------------------ ponte HTTP

class _PedidoFalso(api_bridge._API):
    """Roda uma rota sem abrir socket."""

    def __init__(self, metodo, caminho, corpo=None):
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else b""
        self.command = metodo
        self.path = caminho
        self.headers = {"Content-Length": str(len(dados))}
        self.rfile = io.BytesIO(dados)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status, message=None):
        self.status = status

    def send_header(self, nome, valor):
        pass

    def end_headers(self):
        pass

    def json(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def test_parametro_numerico_invalido_usa_o_padrao():
    pedido = _PedidoFalso("GET", f"/radar/historico?discord_user_id={USUARIO}&limite=abc")
    pedido.do_GET()
    assert pedido.status == 200
    assert pedido.json() == []


def test_erro_inesperado_vira_500_em_json(monkeypatch):
    def quebrar(_id):
        raise RuntimeError("falha de teste")
    monkeypatch.setattr(api_bridge.perfil_mod, "carregar_perfil", quebrar)

    pedido = _PedidoFalso("GET", f"/perfil?discord_user_id={USUARIO}")
    pedido.do_GET()
    assert pedido.status == 500
    assert "falha de teste" in pedido.json()["erro"]


def test_provedor_indisponivel_sem_tratamento_da_rota_vira_503(monkeypatch):
    def sem_provedor():
        raise ProvedorIndisponivel("sem chave")
    monkeypatch.setattr(api_bridge, "obter_provedor", sem_provedor)

    pedido = _PedidoFalso("POST", "/radar/semente", {"discord_user_id": USUARIO})
    pedido.do_POST()
    assert pedido.status == 503
    assert pedido.json()["erro"] == "sem chave"


def test_corpo_que_nao_e_objeto_json_nao_derruba_o_pedido():
    pedido = _PedidoFalso("POST", "/perfil/discovery_level", [1, 2, 3])
    pedido.do_POST()
    assert pedido.status == 200


# ------------------------------------------------------------------ Last.fm

def test_falha_ao_resolver_genero_nao_entra_no_cache(monkeypatch):
    monkeypatch.setattr(lastfm_mod, "_cache_generos", {})
    monkeypatch.setattr(lastfm_mod, "_cache_generos_carregado_de", None)
    provedor = lastfm_mod.ProvedorLastfm()
    respostas = [ProvedorIndisponivel("limite"), {"toptags": {"tag": [{"name": "Rock"}]}}]

    def _get_falso(method, **params):
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    monkeypatch.setattr(provedor, "_get", _get_falso)

    assert provedor.resolver_generos(["Banda"]) == {"banda": []}
    assert provedor.resolver_generos(["Banda"]) == {"banda": ["rock"]}


def test_cache_de_generos_sobrevive_ao_reinicio(monkeypatch):
    monkeypatch.setattr(lastfm_mod, "_cache_generos", {})
    monkeypatch.setattr(lastfm_mod, "_cache_generos_carregado_de", None)
    provedor = lastfm_mod.ProvedorLastfm()
    monkeypatch.setattr(provedor, "_get", lambda method, **params: {"toptags": {"tag": [{"name": "Rock"}]}})
    provedor.resolver_generos(["Banda"])

    # "Reinício": memória vazia, arquivo em disco continua.
    monkeypatch.setattr(lastfm_mod, "_cache_generos", {})
    monkeypatch.setattr(lastfm_mod, "_cache_generos_carregado_de", None)

    def _sem_rede(method, **params):
        raise AssertionError("não deveria chamar o Last.fm")
    monkeypatch.setattr(provedor, "_get", _sem_rede)
    assert provedor.resolver_generos(["Banda"]) == {"banda": ["rock"]}
