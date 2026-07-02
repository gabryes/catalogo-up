import os
import json
import urllib.parse
import urllib.request

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ---------------------------------------------------------------------------
# Configuração de ambiente
# ---------------------------------------------------------------------------
GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID", "")
ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET", "")
ML_REDIRECT_URI = os.environ.get("ML_REDIRECT_URI", "")

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


# ---------------------------------------------------------------------------
# Utilidades de resposta
# ---------------------------------------------------------------------------
def _json_response(status_code, body, extra_headers=None):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def _error_response(status_code, message):
    return _json_response(status_code, {"error": message})


def _get_query_params(event):
    params = event.get("queryStringParameters") or {}
    return params


def _get_body(event):
    body = event.get("body") or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    try:
        return json.loads(body) if body else {}
    except (ValueError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Conexão com Google Sheets
# ---------------------------------------------------------------------------
def _get_google_client():
    if not GOOGLE_SHEETS_KEY:
        raise ValueError("GOOGLE_SHEETS_KEY não definido")
    if not GOOGLE_CREDENTIALS_PATH:
        raise ValueError("GOOGLE_CREDENTIALS_PATH não definido")
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(f"Credenciais não encontradas: {GOOGLE_CREDENTIALS_PATH}")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_PATH, scope
    )
    client = gspread.authorize(credentials)
    return client


def _get_sheet(sheet_name):
    client = _get_google_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
    return spreadsheet.worksheet(sheet_name)


def _rows_to_dicts(rows):
    if not rows or len(rows) < 2:
        return []
    headers = [str(h).strip() for h in rows[0]]
    result = []
    for row in rows[1:]:
        item = {}
        for index, header in enumerate(headers):
            value = row[index] if index < len(row) else ""
            item[header] = value
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Rotas de dados
# ---------------------------------------------------------------------------
def get_services():
    try:
        sheet = _get_sheet("Servicos")
        rows = sheet.get_all_values()
        services = _rows_to_dicts(rows)
        return _json_response(200, {"services": services})
    except ValueError as exc:
        return _error_response(500, str(exc))
    except FileNotFoundError as exc:
        return _error_response(500, str(exc))
    except gspread.exceptions.SpreadsheetNotFound:
        return _error_response(404, "Planilha não encontrada")
    except gspread.exceptions.WorksheetNotFound:
        return _error_response(404, "Aba 'Servicos' não encontrada")
    except Exception as exc:
        return _error_response(500, f"Erro ao buscar serviços: {exc}")


def get_categories():
    try:
        sheet = _get_sheet("Categorias")
        rows = sheet.get_all_values()
        categories = _rows_to_dicts(rows)
        return _json_response(200, {"categories": categories})
    except ValueError as exc:
        return _error_response(500, str(exc))
    except FileNotFoundError as exc:
        return _error_response(500, str(exc))
    except gspread.exceptions.SpreadsheetNotFound:
        return _error_response(404, "Planilha não encontrada")
    except gspread.exceptions.WorksheetNotFound:
        return _error_response(404, "Aba 'Categorias' não encontrada")
    except Exception as exc:
        return _error_response(500, f"Erro ao buscar categorias: {exc}")


# ---------------------------------------------------------------------------
# Rotas de autenticação do Mercado Livre
# ---------------------------------------------------------------------------
def ml_callback(event):
    try:
        params = _get_query_params(event)
        code = params.get("code")
        state = params.get("state")

        if not code:
            error = params.get("error", "unknown_error")
            return _error_response(400, f"Mercado Livre retornou erro: {error}")

        if not ML_CLIENT_ID or not ML_CLIENT_SECRET or not ML_REDIRECT_URI:
            return _error_response(
                500,
                "Variáveis ML_CLIENT_ID, ML_CLIENT_SECRET ou ML_REDIRECT_URI não definidas",
            )

        data = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET,
                "code": code,
                "redirect_uri": ML_REDIRECT_URI,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            ML_TOKEN_URL,
            data=data,
            method="POST",
            headers={"Accept": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        return _json_response(
            200,
            {
                "message": "Autenticação realizada com sucesso",
                "state": state,
                "tokens": token_data,
            },
        )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        return _json_response(
            exc.code,
            {"error": "Erro ao trocar código por token", "details": error_body},
        )
    except Exception as exc:
        return _error_response(500, f"Erro no callback do Mercado Livre: {exc}")


def ml_success(event):
    return _json_response(
        200,
        {"message": "Autenticação concluída com sucesso", "status": "success"},
    )


def ml_error(event):
    params = _get_query_params(event)
    error = params.get("error", "unknown_error")
    error_description = params.get("error_description", "")
    return _json_response(
        400,
        {
            "message": "Falha na autenticação com o Mercado Livre",
            "error": error,
            "error_description": error_description,
        },
    )


# ---------------------------------------------------------------------------
# Roteamento principal
# ---------------------------------------------------------------------------
def _route(path, method, event):
    if method == "OPTIONS":
        return _json_response(204, {})

    if path == "/api/services" and method == "GET":
        return get_services()

    if path == "/api/categories" and method == "GET":
        return get_categories()

    if path == "/callback" and method == "GET":
        return ml_callback(event)

    if path == "/success" and method == "GET":
        return ml_success(event)

    if path == "/error" and method == "GET":
        return ml_error(event)

    return _error_response(404, f"Rota não encontrada: {method} {path}")


def handler(event, context):
    try:
        path = event.get("path", "") or ""
        method = (event.get("httpMethod") or "GET").upper()

        return _route(path, method, event)
    except Exception as exc:
        return _error_response(500, f"Erro interno do servidor: {exc}")