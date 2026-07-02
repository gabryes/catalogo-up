# Script PowerShell para recriar functions/api.py com encoding UTF-8

$ErrorActionPreference = "Stop"

$filePath = Join-Path -Path $PSScriptRoot -ChildPath "functions\api.py"
$dirPath = Split-Path -Parent $filePath

# 1. Remove o arquivo antigo, se existir
if (Test-Path -Path $filePath) {
    Remove-Item -Path $filePath -Force
    Write-Host "Arquivo antigo removido: $filePath"
}

# Garante que o diretorio functions existe
if (-not (Test-Path -Path $dirPath)) {
    New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    Write-Host "Diretorio criado: $dirPath"
}

# 2. Conteudo do novo arquivo functions/api.py
$pythonCode = @'
import os
import json
import urllib.parse
import urllib.request

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Variaveis de ambiente
GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH")
ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET")
ML_REDIRECT_URI = os.environ.get("ML_REDIRECT_URI")


def _json_response(status_code, body):
    """Retorna uma resposta HTTP no formato JSON."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        },
        "body": json.dumps(body, ensure_ascii=False)
    }


def _error_response(status_code, message):
    """Retorna uma resposta de erro padronizada."""
    return _json_response(status_code, {"error": message})


def _get_query_params(event):
    """Extrai os parametros de query string do evento."""
    params = event.get("queryStringParameters") or {}
    if not params:
        raw_query = event.get("rawQueryString") or ""
        if raw_query:
            params = dict(urllib.parse.parse_qsl(raw_query))
    return params


def _get_body(event):
    """Extrai e faz o parse do corpo da requisicao como JSON."""
    raw_body = event.get("body") or ""
    if not raw_body:
        return {}
    if event.get("isBase64Encoded"):
        import base64
        raw_body = base64.b64decode(raw_body).decode("utf-8")
    try:
        return json.loads(raw_body)
    except (ValueError, TypeError):
        return {}


def _get_google_client():
    """Cria e retorna um cliente autenticado do Google Sheets."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_path = GOOGLE_CREDENTIALS_PATH
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError("GOOGLE_CREDENTIALS_PATH nao definido ou arquivo inexistente")
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    return gspread.authorize(creds)


def _get_sheet(client=None, sheet_name=None):
    """Abre a planilha do Google Sheets pelo nome/key."""
    if client is None:
        client = _get_google_client()
    if not GOOGLE_SHEETS_KEY:
        raise RuntimeError("GOOGLE_SHEETS_KEY nao definido")
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
    if sheet_name:
        return spreadsheet.worksheet(sheet_name)
    return spreadsheet.sheet1


def _rows_to_dicts(rows):
    """Converte uma lista de linhas em uma lista de dicionarios usando a primeira linha como cabecalho."""
    if not rows or len(rows) < 2:
        return []
    headers = [str(h).strip() for h in rows[0]]
    result = []
    for row in rows[1:]:
        item = {}
        for idx, header in enumerate(headers):
            value = row[idx] if idx < len(row) else None
            item[header] = value
        result.append(item)
    return result


def get_services():
    """Retorna todos os servicos cadastrados na planilha."""
    try:
        sheet = _get_sheet(sheet_name="Servicos")
        rows = sheet.get_all_values()
        services = _rows_to_dicts(rows)
        return _json_response(200, {"services": services})
    except Exception as exc:
        return _error_response(500, f"Erro ao obter servicos: {exc}")


def get_categories():
    """Retorna todas as categorias cadastradas na planilha."""
    try:
        sheet = _get_sheet(sheet_name="Categorias")
        rows = sheet.get_all_values()
        categories = _rows_to_dicts(rows)
        return _json_response(200, {"categories": categories})
    except Exception as exc:
        return _error_response(500, f"Erro ao obter categorias: {exc}")


def ml_callback():
    """Trata o callback do Mercado Livre e troca o codigo por um token."""
    try:
        code = params.get("code")
        if not code:
            return _error_response(400, "Codigo de autorizacao ausente")

        token_url = "https://api.mercadolibre.com/oauth/token"
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "code": code,
            "redirect_uri": ML_REDIRECT_URI
        }).encode("utf-8")

        req = urllib.request.Request(token_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return _json_response(200, {"auth": payload})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return _error_response(exc.code, f"Erro ML: {body}")
    except Exception as exc:
        return _error_response(500, f"Erro no callback ML: {exc}")


def ml_success():
    """Pagina de sucesso apos autenticacao com o Mercado Livre."""
    return _json_response(200, {"status": "success", "message": "Autenticacao concluida com sucesso"})


def ml_error():
    """Pagina de erro apos falha na autenticacao com o Mercado Livre."""
    error = params.get("error", "unknown_error")
    return _json_response(400, {"status": "error", "message": f"Falha na autenticacao: {error}"})


# Variaveis globais de suporte para rotas que dependem de params/body
params = {}
body = {}


def _route(path, method, event):
    """Realiza o roteamento da requisicao com base no path e no metodo HTTP."""
    global params, body
    params = _get_query_params(event)
    body = _get_body(event)

    normalized_path = (path or "").strip().rstrip("/")
    method_upper = (method or "").upper()

    if method_upper == "OPTIONS":
        return _json_response(204, {})

    if normalized_path == "/services" and method_upper == "GET":
        return get_services()

    if normalized_path == "/categories" and method_upper == "GET":
        return get_categories()

    if normalized_path == "/ml/callback" and method_upper == "GET":
        return ml_callback()

    if normalized_path == "/ml/success" and method_upper == "GET":
        return ml_success()

    if normalized_path == "/ml/error" and method_upper == "GET":
        return ml_error()

    return _error_response(404, f"Rota nao encontrada: {method_upper} {normalized_path}")


def handler(event, context):
    """Handler principal da funcao serverless."""
    try:
        path = event.get("path") or event.get("rawPath") or ""
        method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "GET"
        return _route(path, method, event)
    except Exception as exc:
        return _error_response(500, f"Erro interno: {exc}")
'@

# 3. Salva o novo arquivo com encoding UTF-8 (sem BOM)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($filePath, $pythonCode, $utf8NoBom)

Write-Host "Novo arquivo criado com sucesso: $filePath"
Write-Host "Encoding: UTF-8 (sem BOM)"