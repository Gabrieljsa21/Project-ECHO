# -*- coding: utf-8 -*-
from unittest import mock

from echo.providers.lastfm import ProvedorLastfm, _normalizar_popularidade


def test_listeners_abaixo_do_piso_vira_none():
    assert _normalizar_popularidade(10) is None
    assert _normalizar_popularidade(None) is None
    assert _normalizar_popularidade("não é número") is None


def test_listeners_no_piso_vira_zero():
    assert _normalizar_popularidade(50) == 0


def test_listeners_no_teto_vira_cem():
    assert _normalizar_popularidade(2_000_000) == 100


def test_listeners_acima_do_teto_satura_em_cem():
    assert _normalizar_popularidade(10_000_000) == 100


def test_listeners_intermediario_fica_entre_0_e_100():
    valor = _normalizar_popularidade(100_000)
    assert 0 < valor < 100


def test_obter_faixas_por_tag_le_a_chave_certa_da_resposta():
    """Achado real (2026-08-26, "/caos parou de tocar depois de 1 música") -
    `tag.gettoptracks` devolve `{"tracks": {"track": [...]}}`, NÃO
    `{"toptracks": {...}}` como `artist.gettoptracks` - com a chave errada,
    isso sempre devolveu lista vazia em silêncio, nunca dando candidato de
    gênero pra descoberta/exploração."""
    provedor = ProvedorLastfm()
    resposta_real_da_api = {
        "tracks": {
            "track": [
                {
                    "name": "The One That Got Away", "listeners": "500000",
                    "artist": {"name": "Katy Perry"}, "url": "http://fake",
                },
            ],
        },
    }
    with mock.patch.object(provedor, "_get", return_value=resposta_real_da_api):
        faixas = provedor.obter_faixas_por_tag("pop", limite=15)

    assert len(faixas) == 1
    assert faixas[0]["titulo"] == "The One That Got Away"
    assert faixas[0]["artista"] == "Katy Perry"
    assert faixas[0]["generos"] == ["pop"]
