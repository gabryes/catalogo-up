def load_data():
    import os
    import json
    import gspread

    print("[Catálogo UP] Lendo dados do Google Sheets...")

    creds_dict = None

    # 1. Tentar ler de credentials.json (Desenvolvimento local)
    if os.path.exists('credentials.json'):
        with open('credentials.json', 'r', encoding='utf-8') as f:
            creds_dict = json.load(f)
    # 2. Tentar variável de ambiente GOOGLE_CREDENTIALS_JSON (Netlify)
    else:
        env_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if env_creds:
            # 3. A variável contém o JSON como string
            creds_dict = json.loads(env_creds)

    if not creds_dict:
        raise FileNotFoundError(
            "Credenciais do Google não encontradas. Configure o arquivo 'credentials.json' "
            "localmente ou a variável de ambiente 'GOOGLE_CREDENTIALS_JSON' no Netlify."
        )

    # 4. Usar gspread.service_account_from_dict() para credenciais em dicionário
    gc = gspread.service_account_from_dict(creds_dict)

    sheet_key = os.environ.get('GOOGLE_SHEETS_KEY')
    if not sheet_key:
        raise ValueError("A variável de ambiente 'GOOGLE_SHEETS_KEY' não foi configurada.")

    sh = gc.open_by_key(sheet_key)
    worksheet = sh.get_worksheet(0)
    services = worksheet.get_all_records()

    # Extrair categorias únicas para o filtro
    categories = sorted(list(set(s.get('Categoria', '') for s in services if s.get('Categoria'))))

    return services, categories