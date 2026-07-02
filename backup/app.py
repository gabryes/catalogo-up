import json
import os
import urllib.parse
import urllib.request

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ---------------------------------------------------------------------------
# Configuração via variáveis de ambiente
# ---------------------------------------------------------------------------
GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "google-credentials.json")

ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID", "")
ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET", "")
ML_REDIRECT_URI = os.environ.get("ML_REDIRECT_URI", "")


# ---------------------------------------------------------------------------
# Helpers de resposta HTTP
# ---------------------------------------------------------------------------
def _response(status_code, body, headers=None):
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    if headers:
        default_headers.update(headers)
    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body, ensure_ascii=False),
    }


def _html_response(status_code, html):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
        "body": html,
    }


def _error_response(status_code, message):
    return _response(status_code, {"error": message})


# ---------------------------------------------------------------------------
# Conexão com Google Sheets
# ---------------------------------------------------------------------------
def get_google_sheet():
    """Conecta ao Google Sheets usando gspread + oauth2client."""
    if not GOOGLE_SHEETS_KEY:
        raise ValueError("GOOGLE_SHEETS_KEY não definida.")
    if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise ValueError("GOOGLE_CREDENTIALS_PATH inválido ou arquivo inexistente.")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_PATH, scope
    )
    client = gspread.authorize(credentials)
    return client.open_by_key(GOOGLE_SHEETS_KEY)


def _rows_to_dicts(worksheet):
    """Converte as linhas de uma aba em lista de dicionários usando a primeira linha como header."""
    records = worksheet.get_all_records()
    return records


# ---------------------------------------------------------------------------
# Handlers de domínio
# ---------------------------------------------------------------------------
def handle_services():
    try:
        spreadsheet = get_google_sheet()
        worksheet = spreadsheet.worksheet("services")
        rows = _rows_to_dicts(worksheet)

        services = []
        for row in rows:
            services.append(
                {
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "category": row.get("category", ""),
                    "subcategory": row.get("subcategory", ""),
                    "premium": str(row.get("premium", "")).lower() in ("true", "1", "sim", "yes"),
                    "price": row.get("price", ""),
                    "rating": row.get("rating", ""),
                    "description": row.get("description", ""),
                    "phone": row.get("phone", ""),
                    "whatsapp": row.get("whatsapp", ""),
                    "email": row.get("email", ""),
                    "instagram": row.get("instagram", ""),
                }
            )

        return _response(200, services)
    except ValueError as exc:
        return _error_response(500, str(exc))
    except gspread.exceptions.SpreadsheetNotFound:
        return _error_response(404, "Planilha não encontrada.")
    except gspread.exceptions.WorksheetNotFound:
        return _error_response(404, 'Aba "services" não encontrada.')
    except Exception as exc:
        return _error_response(500, f"Erro ao buscar serviços: {exc}")


def handle_categories():
    try:
        spreadsheet = get_google_sheet()
        worksheet = spreadsheet.worksheet("categories")
        rows = _rows_to_dicts(worksheet)

        categories = []
        for row in rows:
            subcategories_raw = row.get("subcategories", "")
            if isinstance(subcategories_raw, str):
                subcategories = [
                    item.strip()
                    for item in subcategories_raw.split(",")
                    if item.strip()
                ]
            elif isinstance(subcategories_raw, list):
                subcategories = subcategories_raw
            else:
                subcategories = []

            categories.append(
                {
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "icon": row.get("icon", ""),
                    "subcategories": subcategories,
                }
            )

        return _response(200, categories)
    except ValueError as exc:
        return _error_response(500, str(exc))
    except gspread.exceptions.SpreadsheetNotFound:
        return _error_response(404, "Planilha não encontrada.")
    except gspread.exceptions.WorksheetNotFound:
        return _error_response(404, 'Aba "categories" não encontrada.')
    except Exception as exc:
        return _error_response(500, f"Erro ao buscar categorias: {exc}")


def handle_callback(event):
    """Recebe o código de autorização do Mercado Livre e troca por access_token."""
    try:
        if not ML_CLIENT_ID or not ML_CLIENT_SECRET or not ML_REDIRECT_URI:
            return _error_response(500, "Credenciais do Mercado Livre não configuradas.")

        params = event.get("queryStringParameters") or {}
        code = params.get("code")
        if not code:
            return _error_response(400, "Código de autorização ausente.")

        data = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": ML_CLIENT_ID,
                "client_secret": ML_CLIENT_SECRET,
                "code": code,
                "redirect_uri": ML_REDIRECT_URI,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            "https://api.mercadolibre.com/oauth/token",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            token_data = json.loads(body)

        return _response(200, token_data)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        return _error_response(exc.code, f"Erro na autenticação do ML: {err_body}")
    except Exception as exc:
        return _error_response(500, f"Erro no callback: {exc}")


def handle_success():
    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Autenticação concluída</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 60px; }
            .box { max-width: 480px; margin: 0 auto; padding: 40px; border-radius: 8px;
                   background: #f0fdf4; border: 1px solid #bbf7d0; }
            h1 { color: #15803d; }
            p { color: #166534; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Autenticação concluída!</h1>
            <p>Sua conta do Mercado Livre foi conectada com sucesso.</p>
        </div>
    </body>
    </html>
    """
    return _html_response(200, html)


def handle_error(event):
    params = event.get("queryStringParameters") or {}
    reason = params.get("error_description") or params.get("error") or "unknown"
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Erro na autenticação</title>
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 60px; }}
            .box {{ max-width: 480px; margin: 0 auto; padding: 40px; border-radius: 8px;
                   background: #fef2f2; border: 1px solid #fecaca; }}
            h1 {{ color: #b91c1c; }}
            p {{ color: #991b1b; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Erro na autenticação</h1>
            <p>Não foi possível concluir a autenticação com o Mercado Livre.</p>
            <p><strong>Motivo:</strong> {reason}</p>
        </div>
    </body>
    </html>
    """
    return _html_response(400, html)


# ---------------------------------------------------------------------------
# Handler principal do Netlify Function
# ---------------------------------------------------------------------------
def handler(event, context):
    http_method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or ""

    # CORS preflight
    if http_method == "OPTIONS":
        return _response(204, {})

    # Normaliza o path removendo eventual barra final
    normalized_path = path.rstrip("/")

    try:
        if normalized_path.endswith("/api/services") and http_method == "GET":
            return handle_services()

        if normalized_path.endswith("/api/categories") and http_method == "GET":
            return handle_categories()

        if normalized_path.endswith("/callback") and http_method == "POST":
            return handle_callback(event)

        if normalized_path.endswith("/success") and http_method == "GET":
            return handle_success()

        if normalized_path.endswith("/error") and http_method == "GET":
            return handle_error(event)

        return _error_response(404, f"Rota não encontrada: {http_method} {path}")
    except Exception as exc:
        return _error_response(500, f"Erro interno: {exc}")