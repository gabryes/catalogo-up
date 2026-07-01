#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exportador de dados para Google Sheets utilizando autenticação por conta de serviço.

Este script autentica na Google Sheets API via Service Account
(`google.oauth2.service_account.Credentials`) e exporta dados para uma planilha.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configurações globais
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

DEFAULT_CREDENTIALS_FILE = "credentials.json"

# Formato de logging padronizado
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("google_sheets_exporter")


# ---------------------------------------------------------------------------
# Autenticação com conta de serviço
# ---------------------------------------------------------------------------
def get_credentials(credentials_path: str) -> Credentials:
    """
    Carrega as credenciais de conta de serviço a partir de um arquivo JSON.

    Args:
        credentials_path: Caminho para o arquivo de credenciais da conta de serviço.

    Returns:
        Objeto Credentials pronto para uso na Google Sheets API.
    """
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Arquivo de credenciais não encontrado: {credentials_path}"
        )

    logger.info("Carregando credenciais de conta de serviço: %s", credentials_path)
    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )
    logger.info("Credenciais de conta de serviço carregadas com sucesso.")
    return credentials


def get_service(credentials_path: str = DEFAULT_CREDENTIALS_FILE) -> build:
    """
    Constrói o serviço autenticado da Google Sheets API.

    Args:
        credentials_path: Caminho para o arquivo de credenciais da conta de serviço.

    Returns:
        Instância do serviço da Google Sheets API.
    """
    credentials = get_credentials(credentials_path)
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    logger.info("Serviço da Google Sheets API construído com sucesso.")
    return service


# ---------------------------------------------------------------------------
# Operações no Google Sheets
# ---------------------------------------------------------------------------
def create_spreadsheet(service: build, title: str) -> Optional[str]:
    """
    Cria uma nova planilha (spreadsheet) e retorna o seu ID.

    Args:
        service: Serviço autenticado da Google Sheets API.
        title: Título da nova planilha.

    Returns:
        ID da planilha criada ou None em caso de falha.
    """
    spreadsheet_body = {
        "properties": {"title": title},
    }

    try:
        spreadsheet = service.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = spreadsheet.get("spreadsheetId")
        logger.info("Planilha criada: '%s' (ID: %s)", title, spreadsheet_id)
        return spreadsheet_id
    except HttpError as exc:
        logger.error("Erro ao criar planilha: %s", exc)
        return None


def ensure_sheet_exists(
    service: build,
    spreadsheet_id: str,
    sheet_name: str,
) -> int:
    """
    Garante que uma aba com o nome especificado exista na planilha.
    Se não existir, cria a aba.

    Args:
        service: Serviço autenticado da Google Sheets API.
        spreadsheet_id: ID da planilha.
        sheet_name: Nome desejado para a aba.

    Returns:
        ID da aba (sheetId) encontrada ou criada.
    """
    spreadsheet = (
        service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )

    for sheet in spreadsheet.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == sheet_name:
            logger.info("Aba '%s' já existe (sheetId: %s).", sheet_name, properties.get("sheetId"))
            return properties.get("sheetId")

    logger.info("Aba '%s' não encontrada. Criando nova aba...", sheet_name)
    request_body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {"title": sheet_name}
                }
            }
        ]
    }

    response = (
        service.spreadsheets()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
        .execute()
    )
    sheet_id = (
        response.get("replies", [{}])[0]
        .get("addSheet", {})
        .get("properties", {})
        .get("sheetId")
    )
    logger.info("Aba '%s' criada com sucesso (sheetId: %s).", sheet_name, sheet_id)
    return sheet_id


def append_rows(
    service: build,
    spreadsheet_id: str,
    sheet_name: str,
    rows: List[List[Any]],
    value_input_option: str = "USER_ENTERED",
) -> bool:
    """
    Acrescenta linhas de dados em uma aba específica da planilha.

    Args:
        service: Serviço autenticado da Google Sheets API.
        spreadsheet_id: ID da planilha.
        sheet_name: Nome da aba (ex: "Página1").
        rows: Lista de linhas, onde cada linha é uma lista de valores.
        value_input_option: Modo de entrada dos valores (RAW ou USER_ENTERED).

    Returns:
        True se a operação for bem-sucedida, False caso contrário.
    """
    if not rows:
        logger.warning("Nenhuma linha para exportar.")
        return False

    range_name = f"{sheet_name}!A1"
    value_range_body = {
        "values": rows,
    }

    try:
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=value_range_body,
            )
            .execute()
        )
        updated_range = result.get("updates", {}).get("updatedRange", "N/A")
        logger.info("Linhas exportadas com sucesso para %s", updated_range)
        return True
    except HttpError as exc:
        logger.error("Erro ao exportar linhas para Google Sheets: %s", exc)
        return False


def clear_sheet(
    service: build,
    spreadsheet_id: str,
    sheet_name: str,
) -> bool:
    """
    Limpa todos os dados de uma aba específica.

    Args:
        service: Serviço autenticado da Google Sheets API.
        spreadsheet_id: ID da planilha.
        sheet_name: Nome da aba a ser limpa.

    Returns:
        True se a operação for bem-sucedida, False caso contrário.
    """
    range_name = f"{sheet_name}!A1:ZZ"
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={},
        ).execute()
        logger.info("Aba '%s' limpa com sucesso.", sheet_name)
        return True
    except HttpError as exc:
        logger.error("Erro ao limpar aba '%s': %s", sheet_name, exc)
        return False


# ---------------------------------------------------------------------------
# Exportação principal
# ---------------------------------------------------------------------------
def export_data(
    spreadsheet_id: str,
    sheet_name: str,
    rows: List[List[Any]],
    credentials_path: str = DEFAULT_CREDENTIALS_FILE,
    clear_before_export: bool = False,
) -> bool:
    """
    Exporta dados para uma planilha do Google Sheets.

    Args:
        spreadsheet_id: ID da planilha de destino.
        sheet_name: Nome da aba de destino.
        rows: Dados a serem exportados.
        credentials_path: Caminho para o arquivo de credenciais da conta de serviço.
        clear_before_export: Se True, limpa a aba antes de exportar os dados.

    Returns:
        True se a exportação foi bem-sucedida, False caso contrário.
    """
    logger.info("Iniciando exportação para planilha %s", spreadsheet_id)
    service = get_service(credentials_path)

    ensure_sheet_exists(service, spreadsheet_id, sheet_name)

    if clear_before_export:
        clear_sheet(service, spreadsheet_id, sheet_name)

    success = append_rows(service, spreadsheet_id, sheet_name, rows)
    if success:
        logger.info("Exportação concluída com sucesso.")
    else:
        logger.error("Falha na exportação.")
    return success


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main() -> int:
    """
    Fluxo principal do exportador.

    Espera as seguintes variáveis de ambiente:
        - GOOGLE_SHEETS_SPREADSHEET_ID: ID da planilha de destino.
        - GOOGLE_SHEETS_SHEET_NAME: Nome da aba de destino (padrão: "Dados").
        - GOOGLE_APPLICATION_CREDENTIALS: Caminho para o arquivo credentials.json.

    Os dados de exemplo são exportados como demonstração.
    """
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    sheet_name = os.getenv("GOOGLE_SHEETS_SHEET_NAME", "Dados")
    credentials_path = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_CREDENTIALS_FILE
    )

    if not spreadsheet_id:
        logger.error(
            "Variável de ambiente GOOGLE_SHEETS_SPREADSHEET_ID não definida."
        )
        return 1

    # Dados de exemplo para exportação
    sample_data = [
        ["Nome", "Idade", "Cidade"],
        ["Alice", 30, "São Paulo"],
        ["Bob", 25, "Rio de Janeiro"],
        ["Carol", 28, "Belo Horizonte"],
    ]

    success = export_data(
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        rows=sample_data,
        credentials_path=credentials_path,
        clear_before_export=True,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())