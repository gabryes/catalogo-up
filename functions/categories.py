import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH")

def handler(event, context):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
        sheet = spreadsheet.worksheet("Categorias")
        rows = sheet.get_all_values()
        
        if not rows:
            categories = []
        else:
            headers = rows[0]
            categories = []
            for row in rows[1:]:
                category = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
                categories.append(category)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"categories": categories}, ensure_ascii=False)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)})
        }