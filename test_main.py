"""
Testes para main.py

Para rodar:
    pip install pytest
    pytest -v

Pressupõe que este arquivo fica na mesma pasta que main.py
(ou em uma pasta tests/ com main.py importável no PYTHONPATH).
"""

import json
import os
from unittest.mock import patch, Mock

import pytest
import requests

import main


# ---------------------------------------------------------------------------
# gerar_hash
# ---------------------------------------------------------------------------

def test_gerar_hash_e_deterministico():
    dados = {"b": 2, "a": 1}
    assert main.gerar_hash(dados) == main.gerar_hash(dados)


def test_gerar_hash_ignora_ordem_das_chaves():
    dados1 = {"a": 1, "b": 2}
    dados2 = {"b": 2, "a": 1}
    assert main.gerar_hash(dados1) == main.gerar_hash(dados2)


def test_gerar_hash_muda_quando_dados_mudam():
    dados1 = {"a": 1}
    dados2 = {"a": 2}
    assert main.gerar_hash(dados1) != main.gerar_hash(dados2)


# ---------------------------------------------------------------------------
# carregar_controle / salvar_controle
# ---------------------------------------------------------------------------

def test_carregar_controle_retorna_dict_vazio_se_arquivo_nao_existe(tmp_path, monkeypatch):
    caminho = tmp_path / "nao_existe.json"
    monkeypatch.setattr(main, "ARQUIVO_CONTROLE", str(caminho))
    assert main.carregar_controle() == {}


def test_salvar_e_carregar_controle_ida_e_volta(tmp_path, monkeypatch):
    caminho = tmp_path / "controle_teste.json"
    monkeypatch.setattr(main, "ARQUIVO_CONTROLE", str(caminho))

    dados = {"123": {"456": "hashabc"}}
    main.salvar_controle(dados)

    assert caminho.exists()
    assert main.carregar_controle() == dados


# ---------------------------------------------------------------------------
# buscar_ultima_ocorrencia
# ---------------------------------------------------------------------------

def test_buscar_ultima_ocorrencia_sem_value_retorna_none():
    assert main.buscar_ultima_ocorrencia({}) is None
    assert main.buscar_ultima_ocorrencia(None) is None


def test_buscar_ultima_ocorrencia_lista_vazia_retorna_traco():
    ocorrencias = {
        "value": {
            "expedienteProcessoOcorrenciaDto": {"ocorrencias": []}
        }
    }
    assert main.buscar_ultima_ocorrencia(ocorrencias) == "-"


def test_buscar_ultima_ocorrencia_formata_data_corretamente():
    ocorrencias = {
        "value": {
            "expedienteProcessoOcorrenciaDto": {
                "ocorrencias": [
                    {"dataCriacao": "2024-05-10T14:30:00"}
                ]
            }
        }
    }
    resultado = main.buscar_ultima_ocorrencia(ocorrencias)
    assert resultado == "10/05/2024 14:30:00"


# ---------------------------------------------------------------------------
# buscar_ids_processo (mockando requests.get)
# ---------------------------------------------------------------------------

def _mock_response(json_data, ok=True, status_code=200):
    resp = Mock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = Mock()
    if not ok:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError()
    return resp


@patch("main.requests.get")
def test_buscar_ids_processo_sucesso(mock_get):
    mock_get.return_value = _mock_response({
        "success": True,
        "value": {"expedientesProcessos": [{"id": 1}, {"id": 2}]},
    })

    ids = main.buscar_ids_processo("0001234-56.2024.8.11.0001")
    assert ids == [1, 2]


@patch("main.requests.get")
def test_buscar_ids_processo_sem_processos_retorna_lista_vazia(mock_get):
    mock_get.return_value = _mock_response({
        "success": True,
        "value": {"expedientesProcessos": []},
    })

    ids = main.buscar_ids_processo("0001234-56.2024.8.11.0001")
    assert ids == []


@patch("main.requests.get")
def test_buscar_ids_processo_erro_logico_retorna_none(mock_get):
    mock_get.return_value = _mock_response({
        "success": False,
        "errorMessage": "algo deu errado",
    })

    ids = main.buscar_ids_processo("0001234-56.2024.8.11.0001")
    assert ids is None


@patch("main.requests.get")
def test_buscar_ids_processo_timeout_retorna_string_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()

    resultado = main.buscar_ids_processo("0001234-56.2024.8.11.0001")
    assert resultado == "TIMEOUT"


@patch("main.requests.get")
def test_buscar_ids_processo_connection_error_retorna_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError()

    resultado = main.buscar_ids_processo("0001234-56.2024.8.11.0001")
    assert resultado == "TIMEOUT"


# ---------------------------------------------------------------------------
# buscar_ocorrencias (mockando requests.get)
# ---------------------------------------------------------------------------

@patch("main.requests.get")
def test_buscar_ocorrencias_sucesso(mock_get):
    payload = {"success": True, "value": {"expedienteProcessoOcorrenciaDto": {"ocorrencias": []}}}
    mock_get.return_value = _mock_response(payload)

    resultado = main.buscar_ocorrencias(123, "0001234-56.2024.8.11.0001")
    assert resultado == payload


@patch("main.requests.get")
def test_buscar_ocorrencias_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()

    resultado = main.buscar_ocorrencias(123, "0001234-56.2024.8.11.0001")
    assert resultado == "TIMEOUT"


# ---------------------------------------------------------------------------
# monitorar (integração leve, mockando as funções de rede)
# ---------------------------------------------------------------------------

@patch("main.buscar_ocorrencias")
@patch("main.buscar_ids_processo")
def test_monitorar_primeira_consulta_salva_hash(mock_ids, mock_ocorr, tmp_path, monkeypatch):
    caminho = tmp_path / "controle_teste.json"
    monkeypatch.setattr(main, "ARQUIVO_CONTROLE", str(caminho))
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)  # não esperar de verdade

    mock_ids.return_value = [111]
    mock_ocorr.return_value = {
        "success": True,
        "value": {"expedienteProcessoOcorrenciaDto": {"ocorrencias": []}},
    }

    resultado_tabela = []
    main.monitorar("0001234-56.2024.8.11.0001", resultado_tabela)

    controle = main.carregar_controle()
    assert "0001234-56.2024.8.11.0001" in controle
    assert "111" in controle["0001234-56.2024.8.11.0001"]
    assert resultado_tabela[0][2] == "[blue]PRIMEIRA CONSULTA[/blue]"


@patch("main.buscar_ocorrencias")
@patch("main.buscar_ids_processo")
def test_monitorar_detecta_nova_ocorrencia(mock_ids, mock_ocorr, tmp_path, monkeypatch):
    caminho = tmp_path / "controle_teste.json"
    numero = "0001234-56.2024.8.11.0001"

    # já existe um hash antigo salvo para o processo 111
    main_dados_iniciais = {numero: {"111": "hash_antigo_qualquer"}}
    caminho.write_text(json.dumps(main_dados_iniciais), encoding="utf-8")

    monkeypatch.setattr(main, "ARQUIVO_CONTROLE", str(caminho))
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)

    mock_ids.return_value = [111]
    mock_ocorr.return_value = {
        "success": True,
        "value": {"expedienteProcessoOcorrenciaDto": {"ocorrencias": [{"dataCriacao": "2024-01-01T10:00:00"}]}},
    }

    resultado_tabela = []
    main.monitorar(numero, resultado_tabela)

    assert "NOVA OCORRÊNCIA" in resultado_tabela[0][2]