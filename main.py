import requests
import json
import hashlib
import os
import json5
import time
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ENDPOINT")
ARQUIVO_CONTROLE = "controle_ocorrencias.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Connection": "keep-alive"
}

def gerar_hash(dados):
    """Gera hash do JSON para detectar mudanças"""
    json_string = json.dumps(dados, sort_keys=True)
    return hashlib.md5(json_string.encode()).hexdigest()

def carregar_controle():
    if not os.path.exists(ARQUIVO_CONTROLE):
        return {}
    with open(ARQUIVO_CONTROLE, "r") as f:
        return json.load(f)

def salvar_controle(controle):
    with open(ARQUIVO_CONTROLE, "w") as f:
        json.dump(controle, f, indent=4, ensure_ascii=False)

def buscar_ids_processo(numero_unico):
    """Retorna lista de todos os IDs encontrados para o número único."""
    try:
        print(f"[buscar_ids_processo] Buscando processos para {numero_unico}...")
        response = requests.get(
            f"{BASE_URL}/processos-expedientes/filtro",
            params={
                "NumeroUnico": numero_unico,
                "Skip": 0,
                "Take": 10
            },
            headers=HEADERS,
            timeout=(10, 30),
        )
        if not response.ok:
            print(f"[buscar_ids_processo] Status HTTP: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        if not data.get("success", False):
            print("API retornou erro lógico:", data.get("errorMessage"))
            return None  # None = erro lógico, não timeout

        processos = data.get("value", {}).get("expedientesProcessos", [])
        if not processos:
            return []  # Lista vazia = nenhum processo encontrado

        ids = [p["id"] for p in processos]
        print(f"[buscar_ids_processo] {len(ids)} processo(s) encontrado(s): {ids}")
        return ids

    except requests.exceptions.Timeout:
        print(f"[buscar_ids_processo] ⚠️  Timeout ao buscar {numero_unico}. Pulando atualização de hash.")
        return "TIMEOUT"
    except requests.exceptions.ConnectionError:
        print(f"[buscar_ids_processo] ⚠️  Sem conexão ao buscar {numero_unico}. Pulando atualização de hash.")
        return "TIMEOUT"
    except requests.exceptions.RequestException as e:
        print(f"[buscar_ids_processo] Erro na requisição: {e}")
        return "TIMEOUT"


def buscar_ocorrencias(processo_id, numero_unico):
    try:
        print(f"[buscar_ocorrencias] numero={numero_unico}, id={processo_id}")
        response = requests.get(
            f"{BASE_URL}/ocorrencias/id",
            params={"id": processo_id},
            headers=HEADERS,
            timeout=(10, 30),
        )
        if not response.ok:
            print(f"[buscar_ocorrencias] Status HTTP: {response.status_code}")
        response.raise_for_status()

        data = response.json()
        if not data.get("success", True):
            print("API retornou erro lógico:", data.get("errorMessage"))
        return data

    except requests.exceptions.Timeout:
        print(f"[buscar_ocorrencias] ⚠️  Timeout ao buscar ocorrências do processo {processo_id}. Pulando.")
        return "TIMEOUT"
    except requests.exceptions.ConnectionError:
        print(f"[buscar_ocorrencias] ⚠️  Sem conexão ao buscar ocorrências do processo {processo_id}. Pulando.")
        return "TIMEOUT"
    except requests.exceptions.RequestException as e:
        print(f"[buscar_ocorrencias] Erro ao buscar ocorrências: {e}")
        return "TIMEOUT"


def monitorar(numero_unico):
    controle = carregar_controle()

    # Garante que o número único já tem um dict de processos no controle
    if numero_unico not in controle or not isinstance(controle[numero_unico], dict):
        controle[numero_unico] = {}

    ids_resultado = buscar_ids_processo(numero_unico)

    # Timeout ou erro de conexão: não atualiza nada
    if ids_resultado == "TIMEOUT":
        print(f"[monitorar] Ignorando {numero_unico} por falha de rede.")
        return

    if ids_resultado is None:
        print(f"[monitorar] Erro lógico ao buscar processos de {numero_unico}.")
        return

    if not ids_resultado:
        print(f"[monitorar] Nenhum processo encontrado para {numero_unico}.")
        return

    for processo_id in ids_resultado:
        time.sleep(random.uniform(0.21, 0.61))

        ocorrencias = buscar_ocorrencias(processo_id, numero_unico)

        # Timeout ou erro de conexão: não atualiza hash deste processo
        if ocorrencias == "TIMEOUT":
            print(f"[monitorar] Ignorando processo {processo_id} por falha de rede.")
            continue

        if ocorrencias is None:
            print(f"[monitorar] Resposta nula para processo {processo_id}. Ignorando.")
            continue

        novo_hash = gerar_hash(ocorrencias)
        hash_antigo = controle[numero_unico].get(str(processo_id))

        if not hash_antigo:
            print(f"[monitorar] Primeira consulta do processo {processo_id}. Salvando estado.")
            controle[numero_unico][str(processo_id)] = novo_hash
            salvar_controle(controle)
            continue

        if hash_antigo != novo_hash:
            print(f"🚨 🚨 🚨 🚨 Nova ocorrência detectada no processo {processo_id}! 🚨 🚨 🚨 🚨")
            controle[numero_unico][str(processo_id)] = novo_hash
            salvar_controle(controle)
        else:
            print(f"[monitorar] Sem novas ocorrências no processo {processo_id}.")


def carregar_numeros_json(caminho="numeros.json"):
    with open(caminho, "r", encoding="utf-8") as f:
        return json5.load(f)


if __name__ == "__main__":
    inicio = datetime.now()
    print(f"🟢 Script iniciado em: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print("-" * 50)

    numeros = carregar_numeros_json()

    for numero in numeros:
        monitorar(numero)
        time.sleep(2)

    fim = datetime.now()
    duracao = fim - inicio
    print("-" * 50)
    print(f"✅ Script finalizado em: {fim.strftime('%d/%m/%Y %H:%M:%S')} (duração: {str(duracao).split('.')[0]})")
