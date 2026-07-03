#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py - Catálogo UP
Gera o site estático do catálogo a partir de dados do Google Sheets.
"""

import os
import json
import html
import gspread


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")


def get_creds_path():
    """Retorna o caminho do arquivo de credenciais do Google."""
    env_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    local_path = os.path.join(BASE_DIR, "credentials.json")
    if os.path.exists(local_path):
        return local_path
    return None


# ---------------------------------------------------------------------------
# Leitura da planilha
# ---------------------------------------------------------------------------

def ler_planilha():
    """
    Lê os dados do Google Sheets usando gspread com service_account.
    Retorna uma lista de dicionários com os registros da primeira aba.
    """
    creds_path = get_creds_path()
    if not creds_path:
        print("[Catálogo UP] ERRO: Credenciais do Google não encontradas.")
        print("Defina a variável de ambiente GOOGLE_CREDENTIALS_PATH (Netlify) "
              "ou coloque o arquivo credentials.json no diretório do projeto.")
        return None

    sheet_key = os.environ.get("GOOGLE_SHEETS_KEY")
    if not sheet_key:
        print("[Catálogo UP] ERRO: GOOGLE_SHEETS_KEY não definido.")
        print("Defina a variável de ambiente GOOGLE_SHEETS_KEY com o ID da planilha.")
        return None

    print("[Catálogo UP] Lendo dados do Google Sheets...")

    try:
        gc = gspread.service_account(filename=creds_path)
        spreadsheet = gc.open_by_key(sheet_key)
        worksheet = spreadsheet.sheet1
        dados = worksheet.get_all_records()
        print(f"[Catálogo UP] {len(dados)} registros lidos com sucesso.")
        return dados
    except Exception as e:
        print(f"[Catálogo UP] ERRO ao ler a planilha: {e}")
        return None


# ---------------------------------------------------------------------------
# Geração de HTML
# ---------------------------------------------------------------------------

CSS = """
:root {
    --cor-primaria: #e63946;
    --cor-secundaria: #1d3557;
    --cor-fundo: #f1faee;
    --cor-texto: #1d3557;
    --cor-card: #ffffff;
    --cor-sombra: rgba(0, 0, 0, 0.1);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background-color: var(--cor-fundo);
    color: var(--cor-texto);
    line-height: 1.6;
}

.header {
    background: linear-gradient(135deg, var(--cor-secundaria), var(--cor-primaria));
    color: #fff;
    padding: 2rem 1rem;
    text-align: center;
}

.header h1 {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
}

.header p {
    font-size: 1.1rem;
    opacity: 0.9;
}

.container {
    max-width: 1200px;
    margin: 2rem auto;
    padding: 0 1rem;
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1.5rem;
}

.card {
    background: var(--cor-card);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 12px var(--cor-sombra);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 8px 24px var(--cor-sombra);
}

.card-imagem {
    width: 100%;
    height: 220px;
    object-fit: cover;
    background-color: #e9ecef;
}

.card-corpo {
    padding: 1.2rem;
}

.card-titulo {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: var(--cor-secundaria);
}

.card-descricao {
    font-size: 0.95rem;
    color: #555;
    margin-bottom: 1rem;
}

.card-preco {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--cor-primaria);
}

.card-link {
    display: inline-block;
    margin-top: 1rem;
    padding: 0.6rem 1.2rem;
    background-color: var(--cor-primaria);
    color: #fff;
    text-decoration: none;
    border-radius: 8px;
    font-weight: 600;
    transition: background-color 0.3s ease;
}

.card-link:hover {
    background-color: var(--cor-secundaria);
}

.footer {
    background-color: var(--cor-secundaria);
    color: #fff;
    text-align: center;
    padding: 2rem 1rem;
    margin-top: 3rem;
}

.footer p {
    margin-bottom: 1rem;
}

.redes-sociais {
    display: flex;
    justify-content: center;
    gap: 1rem;
}

.redes-sociais a {
    color: #fff;
    font-size: 1.5rem;
    transition: color 0.3s ease, transform 0.3s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background-color: rgba(255, 255, 255, 0.15);
}

.redes-sociais a:hover {
    color: var(--cor-primaria);
    transform: scale(1.15);
    background-color: rgba(255, 255, 255, 0.25);
}

.sem-dados {
    text-align: center;
    padding: 3rem 1rem;
    font-size: 1.2rem;
    color: #888;
}

@media (max-width: 600px) {
    .header h1 {
        font-size: 1.8rem;
    }
    .grid {
        grid-template-columns: 1fr;
    }
}
"""

ICONES_SOCIAIS = """
<div class="redes-sociais">
    <a href="https://www.instagram.com/" target="_blank" rel="noopener noreferrer" aria-label="Instagram">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
        </svg>
    </a>
    <a href="https://www.facebook.com/" target="_blank" rel="noopener noreferrer" aria-label="Facebook">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
            <path d="M9 8h-3v4h3v12h5v-12h3.642l.358-4h-4v-1.667c0-.955.192-1.333 1.115-1.333h2.885v-5h-3.808c-3.596 0-5.192 1.583-5.192 4.615v3.385z"/>
        </svg>
    </a>
    <a href="https://wa.me/" target="_blank" rel="noopener noreferrer" aria-label="WhatsApp">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
            <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.001-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/>
        </svg>
    </a>
</div>
"""


def escapar(texto):
    """Escapa texto para uso seguro em HTML."""
    if texto is None:
        return ""
    return html.escape(str(texto))


def gerar_card(produto):
    """Gera o HTML de um card de produto."""
    nome = escapar(produto.get("nome") or produto.get("Nome") or produto.get("titulo") or "")
    descricao = escapar(produto.get("descricao") or produto.get("Descrição") or produto.get("Descricao") or "")
    preco = escapar(produto.get("preco") or produto.get("Preço") or produto.get("Preco") or "")
    imagem = escapar(produto.get("imagem") or produto.get("Imagem") or produto.get("foto") or "")
    link = escapar(produto.get("link") or produto.get("Link") or produto.get("url") or "")

    imagem_html = f'<img class="card-imagem" src="{imagem}" alt="{nome}" loading="lazy">' if imagem else '<div class="card-imagem"></div>'

    link_html = f'<a class="card-link" href="{link}" target="_blank" rel="noopener noreferrer">Ver mais</a>' if link else ""

    card = f"""
    <div class="card">
        {imagem_html}
        <div class="card-corpo">
            <h3 class="card-titulo">{nome}</h3>
            <p class="card-descricao">{descricao}</p>
            <p class="card-preco">{preco}</p>
            {link_html}
        </div>
    </div>
    """
    return card


def gerar_html(dados):
    """Gera o HTML completo do catálogo a partir dos dados lidos."""
    if not dados:
        cards = '<div class="sem-dados">Nenhum produto encontrado no catálogo.</div>'
    else:
        cards = "\n".join(gerar_card(p) for p in dados)

    html_doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Catálogo UP - Seu catálogo online de produtos.">
    <title>Catálogo UP</title>
    <style>
{CSS}
    </style>
</head>
<body>
    <header class="header">
        <h1>Catálogo UP</h1>
        <p>Seu catálogo online de produtos</p>
    </header>

    <main class="container">
        <div class="grid">
{cards}
        </div>
    </main>

    <footer class="footer">
        <p>&copy; {__import__('datetime').datetime.now().year} Catálogo UP. Todos os direitos reservados.</p>
        {ICONES_SOCIAIS}
    </footer>
</body>
</html>
"""
    return html_doc


# ---------------------------------------------------------------------------
# Escrita do arquivo
# ---------------------------------------------------------------------------

def salvar_html(conteudo):
    """Salva o HTML gerado no diretório public."""
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    caminho = os.path.join(PUBLIC_DIR, "index.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print(f"[Catálogo UP] HTML gerado em: {caminho}")


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------

def main():
    dados = ler_planilha()
    if dados is None:
        raise SystemExit(1)

    html_gerado = gerar_html(dados)
    salvar_html(html_gerado)
    print("[Catálogo UP] Build concluído com sucesso!")


if __name__ == "__main__":
    main()