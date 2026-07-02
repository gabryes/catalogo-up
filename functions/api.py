import os
import json
import urllib.parse
import urllib.request
import gspread
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH")
ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET")
ML_REDIRECT_URI = os.environ.get("ML_REDIRECT_URI")

def _json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps(body, ensure_ascii=False)
    }

def _error_response(status_code, message):
    return _json_response(status_code, {"error": message})

def get_services():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
        sheet = spreadsheet.worksheet("Servicos")
        rows = sheet.get_all_values()
        if not rows:
            return _json_response(200, {"services": []})
        headers = rows[0]
        services = []
        for row in rows[1:]:
            service = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            services.append(service)
        return _json_response(200, {"services": services})
    except Exception as e:
        return _error_response(500, str(e))

def get_categories():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
        sheet = spreadsheet.worksheet("Categorias")
        rows = sheet.get_all_values()
        if not rows:
            return _json_response(200, {"categories": []})
        headers = rows[0]
        categories = []
        for row in rows[1:]:
            category = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            categories.append(category)
        return _json_response(200, {"categories": categories})
    except Exception as e:
        return _error_response(500, str(e))

def handler(event, context):
    path = event.get("path", "")
    method = event.get("httpMethod", "GET")
    
    if method == "OPTIONS":
        return _json_response(204, {})
    
    if path == "/services" and method == "GET":
        return get_services()
    
    if path == "/categories" and method == "GET":
        return get_categories()
    
    return _error_response(404, f"Rota nao encontrada: {method} {path}")