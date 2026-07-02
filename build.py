#!/usr/bin/env python3
"""
build.py - Gera site estático HTML do Catálogo UP a partir de dados do Google Sheets.

Uso:
    python build.py

Requisitos:
    - credentials.json (conta de serviço do Google) na raiz do projeto
    - gspread instalado (pip install gspread)
"""

import json
import os
import re
import shutil
import html
from pathlib import Path

import gspread


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

CREDENTIALS_FILE = "credentials.json"
OUTPUT_DIR = Path("public")
ASSETS_DIR = Path("assets")

# Nome do spreadsheet / abas
SPREADSHEET_NAME = "workbook_v1"
SERVICES_TAB = "workbook_v1__catalogo_1"
CATEGORIES_TAB = "workbook_v1__categorias_4"

# Cores
COLOR_COBALT = "#0055D4"
COLOR_NAVY = "#0B1E40"

# Mapeamento flexível de colunas (minúsculas, sem acento)
SERVICE_ID_KEYS = ["id", "codigo", "code", "slug"]
SERVICE_NAME_KEYS = ["nome", "titulo", "title", "name", "servico"]
SERVICE_DESC_KEYS = ["descricao", "description", "resumo", "desc"]
SERVICE_CATEGORY_KEYS = ["categoria", "category", "categoriaid", "categoria_id"]
SERVICE_LINK_KEYS = ["link", "url", "site", "website"]
SERVICE_CONTACT_KEYS = ["contato", "contact", "email", "telefone"]

CATEGORY_ID_KEYS = ["id", "codigo", "code", "slug"]
CATEGORY_NAME_KEYS = ["nome", "titulo", "title", "name", "categoria"]
CATEGORY_DESC_KEYS = ["descricao", "description", "resumo", "desc"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def esc(text) -> str:
    return html.escape(str(text) if text is not None else "")


def find_value(row: dict, keys: list, default: str = "") -> str:
    row_norm = {normalize(k): v for k, v in row.items()}
    for key in keys:
        nk = normalize(key)
        if nk in row_norm and row_norm[nk] not in (None, ""):
            return str(row_norm[nk]).strip()
    return default


def rows_to_dicts(worksheet) -> list:
    data = worksheet.get_all_values()
    if not data or len(data) < 2:
        return []
    headers = data[0]
    rows = []
    for raw in data[1:]:
        row = {}
        for i, header in enumerate(headers):
            row[header] = raw[i] if i < len(raw) else ""
        if any(v.strip() for v in row.values() if isinstance(v, str)):
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def load_data() -> tuple[list, list]:
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Arquivo '{CREDENTIALS_FILE}' não encontrado. "
            "Coloque as credenciais da conta de serviço do Google na raiz do projeto."
        )

    gc = gspread.service_account(filename=CREDENTIALS_FILE)

    try:
        spreadsheet = gc.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        raise RuntimeError(
            f"Spreadsheet '{SPREADSHEET_NAME}' não encontrado. "
            "Compartilhe a planilha com o e-mail da conta de serviço."
        )

    # Serviços
    try:
        services_ws = spreadsheet.worksheet(SERVICES_TAB)
    except gspread.WorksheetNotFound:
        # fallback: primeira aba
        services_ws = spreadsheet.get_worksheet(0)
    services_raw = rows_to_dicts(services_ws)

    # Categorias
    try:
        categories_ws = spreadsheet.worksheet(CATEGORIES_TAB)
    except gspread.WorksheetNotFound:
        categories_ws = spreadsheet.get_worksheet(1) if len(spreadsheet.worksheets()) > 1 else None
    categories_raw = rows_to_dicts(categories_ws) if categories_ws else []

    # Normaliza categorias
    categories = []
    for row in categories_raw:
        cat_id = find_value(row, CATEGORY_ID_KEYS)
        cat_name = find_value(row, CATEGORY_NAME_KEYS, "Sem categoria")
        if not cat_id:
            cat_id = slugify(cat_name)
        categories.append({
            "id": cat_id,
            "name": cat_name,
            "description": find_value(row, CATEGORY_DESC_KEYS),
        })

    cat_by_id = {normalize(c["id"]): c for c in categories}
    cat_by_name = {normalize(c["name"]): c for c in categories}

    # Normaliza serviços
    services = []
    for row in services_raw:
        sid = find_value(row, SERVICE_ID_KEYS)
        name = find_value(row, SERVICE_NAME_KEYS, "Serviço sem nome")
        if not sid:
            sid = slugify(name)
        else:
            sid = slugify(sid)

        cat_ref = find_value(row, SERVICE_CATEGORY_KEYS)
        category = None
        if cat_ref:
            category = cat_by_id.get(normalize(cat_ref)) or cat_by_name.get(normalize(cat_ref))
        if not category and categories:
            category = categories[0]
        if not category:
            category = {"id": "sem-categoria", "name": "Sem categoria", "description": ""}

        services.append({
            "id": sid,
            "name": name,
            "description": find_value(row, SERVICE_DESC_KEYS),
            "category_id": category["id"],
            "category_name": category["name"],
            "link": find_value(row, SERVICE_LINK_KEYS),
            "contact": find_value(row, SERVICE_CONTACT_KEYS),
        })

    return services, categories


# ---------------------------------------------------------------------------
# Templates / HTML
# ---------------------------------------------------------------------------

CSS = f"""
:root {{
  --cobalt: {COLOR_COBALT};
  --navy: {COLOR_NAVY};
  --bg: #f5f7fb;
  --card: #ffffff;
  --text: #1a2238;
  --muted: #6b7280;
  --border: #e5e7eb;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}}
a {{ color: var(--cobalt); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 1080px; margin: 0 auto; padding: 0 20px; }}

/* Header */
.site-header {{
  background: var(--navy);
  color: #fff;
  padding: 18px 0;
  border-bottom: 4px solid var(--cobalt);
}}
.site-header .container {{
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}}
.site-header .logo {{
  height: 44px;
  width: auto;
  display: block;
}}
.site-header h1 {{
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}}
.site-header .spacer {{ flex: 1; }}
.site-header nav a {{
  color: #fff;
  margin-left: 18px;
  font-size: 0.95rem;
  opacity: 0.9;
}}
.site-header nav a:hover {{ opacity: 1; text-decoration: none; }}

/* Hero / busca */
.hero {{
  background: linear-gradient(135deg, var(--navy), var(--cobalt));
  color: #fff;
  padding: 48px 0 36px;
}}
.hero h2 {{ font-size: 1.8rem; margin-bottom: 8px; }}
.hero p {{ opacity: 0.85; margin-bottom: 22px; }}
.search-box {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}}
.search-box input[type="text"] {{
  flex: 1;
  min-width: 240px;
  padding: 12px 16px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  color: var(--text);
}}
.search-box select {{
  padding: 12px 16px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  color: var(--text);
  background: #fff;
  cursor: pointer;
}}

/* Filtros */
.filters {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 24px 0 8px;
}}
.filter-chip {{
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
}}
.filter-chip:hover {{ border-color: var(--cobalt); color: var(--cobalt); }}
.filter-chip.active {{
  background: var(--cobalt);
  color: #fff;
  border-color: var(--cobalt);
}}

/* Grid de cards */
.section-title {{
  font-size: 1.3rem;
  margin: 32px 0 16px;
  color: var(--navy);
}}
.cards {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
  margin-bottom: 48px;
}}
.card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.card:hover {{
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(11, 30, 64, 0.12);
}}
.card .cat-tag {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--cobalt);
  background: rgba(0, 85, 212, 0.08);
  padding: 3px 10px;
  border-radius: 999px;
  align-self: flex-start;
  margin-bottom: 12px;
}}
.card h3 {{ font-size: 1.1rem; color: var(--navy); margin-bottom: 8px; }}
.card p {{ color: var(--muted); font-size: 0.92rem; flex: 1; }}
.card .card-link {{
  margin-top: 14px;
  font-size: 0.9rem;
  font-weight: 600;
}}
.empty {{
  text-align: center;
  color: var(--muted);
  padding: 40px 0;
}}

/* Página de detalhe */
.detail {{ background: #fff; border: 1px solid var(--border); border-radius: 12px; padding: 32px; margin: 32px 0; }}
.detail .back {{ display: inline-block; margin-bottom: 18px; font-size: 0.9rem; }}
.detail h1 {{ color: var(--navy); margin-bottom: 6px; }}
.detail .meta {{ color: var(--muted); margin-bottom: 20px; }}
.detail .desc {{ margin-bottom: 20px; white-space: pre-line; }}
.detail .actions {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.btn {{
  display: inline-block;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.92rem;
}}
.btn-primary {{ background: var(--cobalt); color: #fff; }}
.btn-primary:hover {{ background: var(--navy); text-decoration: none; color: #fff; }}
.btn-outline {{ border: 1px solid var(--cobalt); color: var(--cobalt); }}
.btn-outline:hover {{ background: var(--cobalt); color: #fff; text-decoration: none; }}

/* Footer */
.site-footer {{
  background: var(--navy);
  color: #fff;
  text-align: center;
  padding: 24px 0;
  font-size: 0.85rem;
  opacity: 0.9;
}}
.site-footer a {{ color: #fff; }}
"""

JS = """
(function () {
  const search = document.getElementById('search');
  const categorySelect = document.getElementById('category-select');
  const chips = document.querySelectorAll('.filter-chip');
  const cards = Array.from(document.querySelectorAll('.card'));
  const empty = document.getElementById('empty-state');

  function applyFilters() {
    const term = (search ? search.value : '').toLowerCase().trim();
    let activeCat = 'all';
    if (categorySelect) activeCat = categorySelect.value;
    const activeChip = document.querySelector('.filter-chip.active');
    if (activeChip) activeCat = activeChip.getAttribute('data-cat');

    let visible = 0;
    cards.forEach(function (card) {
      const name = (card.getAttribute('data-name') || '').toLowerCase();
      const desc = (card.getAttribute('data-desc') || '').toLowerCase();
      const cat = card.getAttribute('data-cat') || '';
      const matchTerm = !term || name.includes(term) || desc.includes(term);
      const matchCat = activeCat === 'all' || cat === activeCat;
      const show = matchTerm && matchCat;
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    if (empty) empty.style.display = visible === 0 ? '' : 'none';
  }

  if (search) search.addEventListener('input', applyFilters);
  if (categorySelect) categorySelect.addEventListener('change', function () {
    chips.forEach(c => c.classList.remove('active'));
    applyFilters();
  });
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      if (categorySelect) categorySelect.value = chip.getAttribute('data-cat');
      applyFilters();
    });
  });
})();
"""


def header_html(active: str = "home") -> str:
    nav = [
        ("home", "Início", "index.html"),
        ("services", "Serviços", "services/index.html"),
    ]
    nav_links = "".join(
        f'<a href="{href}" style="{"opacity:1;font-weight:600;" if active == key else ""}">{label}</a>'
        for key, label, href in nav
    )
    return f"""
    <header class="site-header">
      <div class="container">
        <img src="logo_1.png" alt="Catálogo UP" class="logo" onerror="this.style.display='none'">
        <h1>Catálogo UP</h1>
        <div class="spacer"></div>
        <nav>{nav_links}</nav>
      </div>
    </header>
    """


def footer_html() -> str:
    return """
    <footer class="site-footer">
      <div class="container">Catálogo UP &middot; Gerado a partir do Google Sheets</div>
    </footer>
    """


def page_template(title: str, body: str, active: str = "home") -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)} - Catálogo UP</title>
  <link rel="icon" href="logo_1.png" type="image/png">
  <style>{CSS}</style>
</head>
<body>
{header_html(active)}
{body}
{footer_html()}
</body>
</html>
"""


def card_html(service: dict, depth_prefix: str = "") -> str:
    return f"""
    <article class="card" data-name="{esc(service['name'])}" data-desc="{esc(service['description'])}" data-cat="{esc(service['category_id'])}">
      <span class="cat-tag">{esc(service['category_name'])}</span>
      <h3>{esc(service['name'])}</h3>
      <p>{esc(service['description'][:160])}{('...' if len(service['description']) > 160 else '')}</p>
      <a class="card-link" href="{depth_prefix}services/{esc(service['id'])}/index.html">Ver detalhes &rarr;</a>
    </article>
    """


def build_index(services: list, categories: list) -> str:
    chips = '<button class="filter-chip active" data-cat="all">Todas</button>' + "".join(
        f'<button class="filter-chip" data-cat="{esc(c["id"])}">{esc(c["name"])}</button>'
        for c in categories
    )
    options = '<option value="all">Todas as categorias</option>' + "".join(
        f'<option value="{esc(c["id"])}">{esc(c["name"])}</option>'
        for c in categories
    )
    cards = "".join(card_html(s, depth_prefix="") for s in services)

    body = f"""
    <section class="hero">
      <div class="container">
        <h2>Encontre o serviço que você precisa</h2>
        <p>Catálogo de serviços disponíveis na plataforma UP.</p>
        <div class="search-box">
          <input type="text" id="search" placeholder="Buscar por nome ou descrição...">
          <select id="category-select">
            {options}
          </select>
        </div>
      </div>
    </section>

    <main class="container">
      <div class="filters">{chips}</div>
      <h2 class="section-title">Serviços</h2>
      <div class="cards" id="cards">
        {cards}
      </div>
      <div class="empty" id="empty-state" style="display:none;">
        Nenhum serviço encontrado para a sua busca.
      </div>
    </main>
    <script>{JS}</script>
    """
    return page_template("Início", body, active="home")


def build_services_page(services: list, categories: list) -> str:
    chips = '<button class="filter-chip active" data-cat="all">Todas</button>' + "".join(
        f'<button class="filter-chip" data-cat="{esc(c["id"])}">{esc(c["name"])}</button>'
        for c in categories
    )
    options = '<option value="all">Todas as categorias</option>' + "".join(
        f'<option value="{esc(c["id"])}">{esc(c["name"])}</option>'
        for c in categories
    )
    cards = "".join(card_html(s, depth_prefix="") for s in services)

    body = f"""
    <section class="hero">
      <div class="container">
        <h2>Todos os serviços</h2>
        <p>Lista completa de serviços do Catálogo UP.</p>
        <div class="search-box">
          <input type="text" id="search" placeholder="Buscar serviços...">
          <select id="category-select">
            {options}
          </select>
        </div>
      </div>
    </section>

    <main class="container">
      <div class="filters">{chips}</div>
      <div class="cards" id="cards">
        {cards}
      </div>
      <div class="empty" id="empty-state" style="display:none;">
        Nenhum serviço encontrado.
      </div>
    </main>
    <script>{JS}</script>
    """
    return page_template("Serviços", body, active="services")


def build_service_detail(service: dict) -> str:
    actions = []
    if service.get("link"):
        actions.append(f'<a class="btn btn-primary" href="{esc(service["link"])}" target="_blank" rel="noopener">Acessar serviço</a>')
    if service.get("contact"):
        actions.append(f'<span class="btn btn-outline">Contato: {esc(service["contact"])}</span>')
    actions_html = "\n".join(actions) if actions else "<span class=\"btn btn-outline\">Sem informações adicionais</span>"

    body = f"""
    <main class="container">
      <article class="detail">
        <a class="back" href="../../index.html">&larr; Voltar ao início</a>
        <a class="back" href="../index.html" style="margin-left:10px;">&larr; Todos os serviços</a>
        <span class="cat-tag" style="display:inline-block;font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:var(--cobalt);background:rgba(0,85,212,0.08);padding:3px 10px;border-radius:999px;margin-bottom:12px;">{esc(service['category_name'])}</span>
        <h1>{esc(service['name'])}</h1>
        <p class="meta">Categoria: {esc(service['category_name'])}</p>
        <div class="desc">{esc(service['description']) or 'Sem descrição disponível.'}</div>
        <div class="actions">{actions_html}</div>
      </article>
    </main>
    """
    return page_template(service["name"], body, active="services")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def copy_assets():
    """Copia logos e demais assets para a pasta public/."""
    if ASSETS_DIR.exists():
        for asset in ASSETS_DIR.iterdir():
            if asset.is_file():
                shutil.copy2(asset, OUTPUT_DIR / asset.name)

    # Copia logos comuns se existirem na raiz
    for logo in ("logo_1.png", "logo_2.png"):
        if os.path.exists(logo):
            shutil.copy2(logo, OUTPUT_DIR / logo)


def build_site():
    print("[Catálogo UP] Lendo dados do Google Sheets...")
    services, categories = load_data()
    print(f"  -> {len(services)} serviços")
    print(f"  -> {len(categories)} categorias")

    if not services:
        print("[Aviso] Nenhum serviço encontrado. O site será gerado vazio.")

    # Limpa e recria a pasta public/
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Copia assets
    copy_assets()

    # index.html
    (OUTPUT_DIR / "index.html").write_text(build_index(services, categories), encoding="utf-8")
    print("  -> public/index.html")

    # /services/index.html
    services_dir = OUTPUT_DIR / "services"
    services_dir.mkdir(exist_ok=True)
    (services_dir / "index.html").write_text(build_services_page(services, categories), encoding="utf-8")
    print("  -> public/services/index.html")

    # /services/[id]/index.html
    for service in services:
        sdir = services_dir / service["id"]
        sdir.mkdir(exist_ok=True)
        (sdir / "index.html").write_text(build_service_detail(service), encoding="utf-8")
        print(f"  -> public/services/{service['id']}/index.html")

    print("[Catálogo UP] Site estático gerado com sucesso em 'public/'.")


if __name__ == "__main__":
    build_site()