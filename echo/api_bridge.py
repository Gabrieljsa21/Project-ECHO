# -*- coding: utf-8 -*-
"""Ponte HTTP do ECHO (porta 8774) - mesmo padrão de `hestia/api_bridge.py`
(`BaseHTTPRequestHandler` simples, sem framework). Único consumidor: a GAIA
(`integrations/echo_client.py`) - ela decide QUANDO gerar o Radar (Agendador Diário
ou comando do usuário) e COMO apresentar (persona, explicação, seção 13 do
ECHO_SPEC); aqui só o ranking determinístico e a persistência."""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from echo.core import perfil as perfil_mod
from echo.core import radar as radar_mod
from echo.core import feedback as feedback_mod
from echo.core import historico as historico_mod
from echo.providers import obter_provedor, ProvedorIndisponivel

LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 8774


def _ler_corpo_json(handler):
    tamanho = int(handler.headers.get("Content-Length", 0))
    try:
        return json.loads(handler.rfile.read(tamanho)) if tamanho else {}
    except Exception:
        return {}


def _coletar_candidatos(provedor, perfil, limite_geral=40):
    """Lançamentos gerais + busca dedicada pelos artistas favoritos - senão o Radar
    nunca saberia de música nova de quem o usuário já gosta, só do que o provedor
    considera "lançamento em destaque" globalmente. Para na primeira falha do
    provedor no meio do loop (ex.: rate limit) e segue com o que já tiver coletado,
    em vez de derrubar a geração do Radar inteira."""
    candidatos = list(provedor.obter_lancamentos_novos(limite_geral))
    for artista in perfil["favorite_artists"][:10]:
        try:
            candidatos.extend(provedor.buscar_faixa(f'artist:"{artista["nome"]}"'))
        except ProvedorIndisponivel:
            break
    return candidatos


class _API(BaseHTTPRequestHandler):
    def _responder_json(self, dados, status=200):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)

    def _responder_404(self):
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        caminho, _, query = self.path.partition("?")
        params = urllib.parse.parse_qs(query)

        if caminho == "/status":
            self._responder_json({"provedor_configurado": obter_provedor().esta_configurado()})
        elif caminho == "/perfil":
            self._responder_json(perfil_mod.carregar_perfil())
        elif caminho == "/radar/atual":
            forcar = (params.get("forcar") or ["0"])[0] == "1"
            if not forcar and radar_mod.radar_ja_gerado_hoje():
                self._responder_json({"radar": radar_mod.obter_ultimo_radar(), "novo": False})
                return
            try:
                provedor = obter_provedor()
                perfil = perfil_mod.carregar_perfil()
                candidatos = _coletar_candidatos(provedor, perfil)
                radar = radar_mod.gerar_radar(candidatos)
                self._responder_json({"radar": radar, "novo": True})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e), "radar": []}, status=503)
        elif caminho == "/radar/historico":
            limite = int((params.get("limite") or [20])[0])
            self._responder_json(historico_mod.obter_historico(limite))
        else:
            self._responder_404()

    def do_POST(self):
        caminho = self.path
        corpo = _ler_corpo_json(self)

        if caminho == "/perfil/artista_favorito":
            self._responder_json(perfil_mod.adicionar_artista_favorito(corpo.get("nome", ""), corpo.get("genero")))
        elif caminho == "/perfil/artista_rejeitado":
            self._responder_json(perfil_mod.adicionar_artista_rejeitado(corpo.get("nome", "")))
        elif caminho == "/perfil/genero":
            self._responder_json(perfil_mod.definir_peso_genero(corpo.get("nome", ""), float(corpo.get("peso", 0.5))))
        elif caminho == "/perfil/discovery_level":
            self._responder_json(perfil_mod.definir_discovery_level(float(corpo.get("valor", 0.5))))
        elif caminho == "/radar/feedback":
            entrada = feedback_mod.processar_feedback(
                corpo.get("track_id", ""), corpo.get("feedback", ""), corpo.get("genero"),
            )
            if entrada is None:
                self._responder_404()
            else:
                self._responder_json(entrada)
        else:
            self._responder_404()

    def log_message(self, format, *args):
        return


def iniciar_servidor_api():
    servidor = HTTPServer((LOCAL_API_HOST, LOCAL_API_PORT), _API)
    servidor.serve_forever()
