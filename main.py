import requests
import json
import hashlib
import os
import json5
import time
import random
from datetime import datetime
from dotenv import load_dotenv

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live
from rich.text import Text
from rich import box
from rich.rule import Rule
from rich.columns import Columns
from rich.align import Align
from rich.markup import escape

load_dotenv()

console = Console()

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
        console.print(f"  [cyan]↳ Buscando processos para[/cyan] [bold white]{escape(numero_unico)}[/bold white]...")
        response = requests.get(
            f"{BASE_URL}/processos-expedientes/filtro",
            params={"NumeroUnico": numero_unico, "Skip": 0, "Take": 10},
            headers=HEADERS,
            timeout=(10, 30),
        )
        if not response.ok:
            console.print(f"  [red]✗ HTTP {response.status_code}[/red]")
        response.raise_for_status()
        data = response.json()

        if not data.get("success", False):
            console.print(f"  [red]✗ Erro lógico da API:[/red] {escape(str(data.get('errorMessage', '?')))}")
            return None

        processos = data.get("value", {}).get("expedientesProcessos", [])
        if not processos:
            return []

        ids = [p["id"] for p in processos]
        console.print(f"  [green]✓[/green] {len(ids)} processo(s) encontrado(s): [dim]{ids}[/dim]")
        return ids

    except requests.exceptions.Timeout:
        console.print("  [yellow]⚠ Timeout ao buscar processos. Pulando.[/yellow]")
        return "TIMEOUT"
    except requests.exceptions.ConnectionError:
        console.print("  [yellow]⚠ Sem conexão. Pulando.[/yellow]")
        return "TIMEOUT"
    except requests.exceptions.RequestException as e:
        console.print(f"  [red]✗ Erro na requisição:[/red] {escape(str(e))}")
        return "TIMEOUT"


def buscar_ocorrencias(processo_id, numero_unico):
    try:
        console.print(f"    [dim]→ Buscando ocorrências do processo[/dim] [bold]{processo_id}[/bold]...")
        response = requests.get(
            f"{BASE_URL}/ocorrencias/id",
            params={"id": processo_id},
            headers=HEADERS,
            timeout=(10, 30),
        )
        if not response.ok:
            console.print(f"    [red]✗ HTTP {response.status_code}[/red]")
        response.raise_for_status()
        data = response.json()
        if not data.get("success", True):
            console.print(f"    [red]✗ Erro lógico:[/red] {escape(str(data.get('errorMessage', '?')))}")
        return data

    except requests.exceptions.Timeout:
        console.print(f"    [yellow]⚠ Timeout no processo {processo_id}. Pulando.[/yellow]")
        return "TIMEOUT"
    except requests.exceptions.ConnectionError:
        console.print(f"    [yellow]⚠ Sem conexão no processo {processo_id}. Pulando.[/yellow]")
        return "TIMEOUT"
    except requests.exceptions.RequestException as e:
        console.print(f"    [red]✗ Erro:[/red] {escape(str(e))}")
        return "TIMEOUT"


def monitorar(numero_unico, resultado_tabela):
    """Monitora um número único e registra o resultado na tabela de resumo."""
    controle = carregar_controle()

    if numero_unico not in controle or not isinstance(controle[numero_unico], dict):
        controle[numero_unico] = {}

    ids_resultado = buscar_ids_processo(numero_unico)

    if ids_resultado == "TIMEOUT":
        console.print(f"  [yellow]⚠ Ignorando {escape(numero_unico)} por falha de rede.[/yellow]")
        resultado_tabela.append((numero_unico, "–", "[yellow]TIMEOUT[/yellow]", "-"))
        return

    if ids_resultado is None:
        console.print(f"  [red]✗ Erro lógico ao buscar processos de {escape(numero_unico)}.[/red]")
        resultado_tabela.append((numero_unico, "–", "[red]ERRO LÓGICO[/red]", "-"))
        return

    if not ids_resultado:
        console.print(f"  [dim]Nenhum processo encontrado para {escape(numero_unico)}.[/dim]")
        resultado_tabela.append((numero_unico, "0", "[dim]Sem processos[/dim]", "-"))
        return

    for processo_id in ids_resultado:
        time.sleep(random.uniform(0.21, 0.61))
        ocorrencias = buscar_ocorrencias(processo_id, numero_unico)

        if ocorrencias == "TIMEOUT":
            console.print(f"    [yellow]⚠ Ignorando processo {processo_id} por falha de rede.[/yellow]")
            resultado_tabela.append((numero_unico, str(processo_id), "[yellow]TIMEOUT[/yellow]", "-"))
            continue

        if ocorrencias is None:
            console.print(f"    [red]✗ Resposta nula para processo {processo_id}.[/red]")
            resultado_tabela.append((numero_unico, str(processo_id), "[red]NULO[/red]", "-"))
            continue
        ultima_ocorrencia = buscar_ultima_ocorrencia(ocorrencias)

        novo_hash = gerar_hash(ocorrencias)
        hash_antigo = controle[numero_unico].get(str(processo_id))

        if not hash_antigo:
            console.print(
                f"    [blue]ℹ Primeira consulta do processo {processo_id}. Estado salvo.[/blue]"
            )
            controle[numero_unico][str(processo_id)] = novo_hash
            salvar_controle(controle)
            resultado_tabela.append((numero_unico, str(processo_id), "[blue]PRIMEIRA CONSULTA[/blue]", ultima_ocorrencia))
            continue

        if hash_antigo != novo_hash:
            alerta = Panel(
                f"[bold red]Nova ocorrência detectada![/bold red]\n"
                f"Processo: [bold]{processo_id}[/bold]\n"
                f"Número: [bold]{escape(numero_unico)}[/bold]",
                title="[blink]🚨 ALERTA 🚨[/blink]",
                border_style="red",
                expand=False,
            )
            console.print(alerta)
            controle[numero_unico][str(processo_id)] = novo_hash
            salvar_controle(controle)
            resultado_tabela.append((numero_unico, str(processo_id), "[bold red]🚨 NOVA OCORRÊNCIA[/bold red]", ultima_ocorrencia))
        else:
            console.print(
                f"    [green]✓ Sem mudanças no processo {processo_id}.[/green]"
            )
            resultado_tabela.append((numero_unico, str(processo_id), "[green]✓ Sem mudanças[/green]", ultima_ocorrencia))


def carregar_numeros_json(caminho="numeros.json"):
    with open(caminho, "r", encoding="utf-8") as f:
        return json5.load(f)


def buscar_ultima_ocorrencia(ocorrencias):
    """Retorna a última ocorrência de um processo, se houver."""
    if not ocorrencias or "value" not in ocorrencias:
        return None

    value = ocorrencias["value"]["expedienteProcessoOcorrenciaDto"]["ocorrencias"]
    
    if isinstance(value, list) and value and "dataCriacao" in value[0]:
        data = value[0]["dataCriacao"]
        dt = datetime.fromisoformat(data)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    return "-"

def imprimir_tabela_resumo(resultados):
    table = Table(
        title="Resumo da Execução",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Número Único", style="white", no_wrap=True)
    table.add_column("Processo ID", justify="center", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Data última ocorrência", justify="center")

    for numero, proc_id, status, data_ultima_ocorrencia in resultados:
        table.add_row(numero, proc_id, status, data_ultima_ocorrencia)

    console.print()
    console.print(table)


if __name__ == "__main__":
    inicio = datetime.now()

    console.print()
    console.print(
        Panel(
            Align.center(
                Text("Monitor de Ocorrências Judiciais", style="bold white")
            ),
            subtitle=f"[dim]Iniciado em {inicio.strftime('%d/%m/%Y %H:%M:%S')}[/dim]",
            border_style="green",
            padding=(1, 4),
        )
    )
    console.print()

    numeros = carregar_numeros_json()
    total = len(numeros)
    resultado_tabela = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        tarefa = progress.add_task("[cyan]Monitorando processos...", total=total)

        for i, numero in enumerate(numeros, 1):
            console.print(Rule(f"[bold cyan]{escape(numero)}[/bold cyan] ({i}/{total})", style="cyan"))
            monitorar(numero, resultado_tabela)
            progress.advance(tarefa)
            if i < total:
                time.sleep(2)

    fim = datetime.now()
    duracao = fim - inicio

    imprimir_tabela_resumo(resultado_tabela)

    console.print()
    console.print(
        Panel(
            f"[green]✅ Script finalizado em[/green] [bold]{fim.strftime('%d/%m/%Y %H:%M:%S')}[/bold]\n"
            f"[dim]Duração total: {str(duracao).split('.')[0]}[/dim]",
            border_style="green",
            expand=False,
        )
    )
    console.print()