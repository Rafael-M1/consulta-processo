import requests
import json
import hashlib
import os
import json5
import time
import random
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
        json.dump(controle, f, indent=4)

def buscar_id_processo(numero_unico):
    try:
        print(f"[buscar_id_processo] ")
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

        print(f"[buscar_id_processo] Status HTTP: {response.status_code}")

        response.raise_for_status()

        data = response.json()

        if not data.get("success", False):
            print("API retornou erro lógico:", data.get("errorMessage"))
            return None

        processos = data.get("value", {}).get("expedientesProcessos", [])

        if not processos:
            return None

        return processos[0]["id"]

    except requests.exceptions.RequestException as e:
        print("Erro na requisição:", e)
        return None

def buscar_ocorrencias(processo_id):
    try:
        print(f"[buscar_ocorrencias] ")
        response = requests.get(
            f"{BASE_URL}/ocorrencias/id",
            params={"id": processo_id},
            headers=HEADERS,
            timeout=(10, 30),
        )

        print(f"[buscar_ocorrencias] Status HTTP: {response.status_code}")

        response.raise_for_status()

        data = response.json()

        if not data.get("success", True):
            print("API retornou erro lógico:", data.get("errorMessage"))

        return data

    except requests.exceptions.RequestException as e:
        print("Erro ao buscar ocorrências:", e)
        return None

def monitorar(numero_unico):
    controle = carregar_controle()

    processo_id = buscar_id_processo(numero_unico)
    if not processo_id:
        print("Processo não encontrado.")
        return
    
    time.sleep(random.uniform(0.21, 0.61))

    ocorrencias = buscar_ocorrencias(processo_id)
    novo_hash = gerar_hash(ocorrencias)

    hash_antigo = controle.get(numero_unico)

    if not hash_antigo:
        print("Primeira consulta. Salvando estado.")
        controle[numero_unico] = novo_hash
        salvar_controle(controle)
        return

    if hash_antigo != novo_hash:
        print("🚨 Nova ocorrência detectada!")
        controle[numero_unico] = novo_hash
        salvar_controle(controle)
    else:
        print("Sem novas ocorrências.")
        
def carregar_numeros_json(caminho="numeros.json"):
    with open("numeros.json", "r", encoding="utf-8") as f:
        return json5.load(f)

if __name__ == "__main__":
    numeros = carregar_numeros_json()

    resultados = []

    for numero in numeros:
        monitorar(numero)
        time.sleep(2)
