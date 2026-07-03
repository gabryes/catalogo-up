#!/usr/bin/env python3
"""
Catálogo UP - Build Script
Gera páginas estáticas (index + detalhes) a partir de dados do Google Sheets.
"""

import os
import re
import json
import html
import shutil
from pathlib import Path

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    gspread = None
    ServiceAccountCredentials = None

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()
PUBLIC_DIR = BASE_DIR / "public"
SERVICES_DIR = PUBLIC_DIR / "services"
ASSETS_DIR = PUBLIC_DIR / "assets"

GOOGLE_SHEETS_KEY = os.environ.get("GOOGLE_SHEETS_KEY", "")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")

# Colunas esperadas na planilha
COLUMN_MAP = {
    "nome": ["nome", "name", "titulo", "title"],
    "categoria": ["categoria", "category", "tipo"],
    "descricao": ["descricao", "description", "desc"],
    "telefone": ["telefone", "phone", "tel", "whatsapp"],
    "email": ["email", "e-mail", "mail"],
    "endereco": ["endereco", "address", "local", "localizacao"],
    "horario": ["horario", "horários", "hours", "funcionamento"],
    "instagram": ["instagram", "insta", "ig"],
    "whatsapp": ["whatsapp", "wpp", "wa", "zap"],
}

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Converte texto em slug amigável para URL."""
    if not text:
        return "servico"
    text = str(text).lower().strip()
    text = re.sub(r"[áàâãä]", "a", text)
    text = re.sub(r"[éèêë]", "e", text)
    text = re.sub(r"[íìîï]", "i", text)
    text = re.sub(r"[óòôõö]", "o", text)
    text = re.sub(r"[úùûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text or "servico"


def ensure_unique_slug(base_slug: str, existing_slugs: set) -> str:
    """Garante que o slug seja único."""
    slug = base_slug
    counter = 2
    while slug in existing_slugs:
        slug = f"{base_slug}-{counter}"
        counter += 1
    existing_slugs.add(slug)
    return slug


def esc(text) -> str:
    """Escapa HTML."""
    return html.escape(str(text)) if text else ""


def truncate(text: str, max_len: int = 100) -> str:
    """Trunca texto para descrição resumida."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def normalize_row(headers: list, row: list) -> dict:
    """Normaliza uma linha da planilha para um dict com chaves padrão."""
    result = {key: "" for key in COLUMN_MAP.keys()}
    header_lower = [str(h).lower().strip() if h else "" for h in headers]

    for field, aliases in COLUMN_MAP.items():
        for i, h in enumerate(header_lower):
            if h in aliases and i < len(row):
                result[field] = str(row[i]).strip() if row[i] else ""
                break
    return result


# ---------------------------------------------------------------------------
# Leitura do Google Sheets
# ---------------------------------------------------------------------------

def get_credentials_path() -> str:
    """Retorna o caminho das credenciais do Google."""
    if GOOGLE_CREDENTIALS_PATH and os.path.exists(GOOGLE_CREDENTIALS_PATH):
        return GOOGLE_CREDENTIALS_PATH
    local = BASE_DIR / "credentials.json"
    if local.exists():
        return str(local)
    return ""


def read_google_sheets() -> list:
    """Lê dados do Google Sheets e retorna lista de serviços normalizados."""
    if not gspread:
        print("[Catálogo UP] AVISO: gspread não instalado. Usando dados de exemplo.")
        return get_sample_data()

    cred_path = get_credentials_path()
    if not cred_path:
        print("[Catálogo UP] AVISO: Credenciais do Google não encontradas.")
        print("Defina GOOGLE_CREDENTIALS_PATH ou coloque credentials.json no projeto.")
        print("Usando dados de exemplo para não falhar o build.")
        return get_sample_data()

    if not GOOGLE_SHEETS_KEY:
        print("[Catálogo UP] AVISO: GOOGLE_SHEETS_KEY não definida. Usando dados de exemplo.")
        return get_sample_data()

    try:
        print("[Catálogo UP] Lendo dados do Google Sheets...")
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEETS_KEY).sheet1
        data = sheet.get_all_values()

        if not data or len(data) < 2:
            print("[Catálogo UP] Planilha vazia. Usando dados de exemplo.")
            return get_sample_data()

        headers = data[0]
        services = []
        for row in data[1:]:
            if not any(cell.strip() for cell in row):
                continue
            services.append(normalize_row(headers, row))

        print(f"[Catálogo UP] {len(services)} serviços lidos da planilha.")
        return services

    except Exception as e:
        print(f"[Catálogo UP] ERRO ao ler planilha: {e}")
        print("Usando dados de exemplo.")
        return get_sample_data()


def get_sample_data() -> list:
    """Dados de exemplo para quando não há credenciais."""
    return [
        {
            "nome": "Maria Costureira",
            "categoria": "Costureira",
            "descricao": "Costura, consertos, ajustes e reformas de roupas em geral. Atendimento rápido e de qualidade.",
            "telefone": "(11) 99999-9999",
            "email": "maria@email.com",
            "endereco": "Rua das Flores, 123 - Centro",
            "horario": "Seg a Sex: 8h às 18h",
            "instagram": "https://instagram.com/mariacostureira",
            "whatsapp": "5511999999999",
        },
        {
            "nome": "João Encanador",
            "categoria": "Encanador",
            "descricao": "Serviços de hidráulica, reparos de vazamentos, instalação de torneiras e caixas de descarga.",
            "telefone": "(11) 88888-8888",
            "email": "joao@email.com",
            "endereco": "Av. Brasil, 456 - Bairro Novo",
            "horario": "Seg a Sáb: 7h às 19h",
            "instagram": "",
            "whatsapp": "5511888888888",
        },
        {
            "nome": "Ana Cabeleireira",
            "categoria": "Beleza",
            "descricao": "Cortes, coloração, tratamentos capilares e penteados para todas as ocasiões.",
            "telefone": "(11) 77777-7777",
            "email": "ana@email.com",
            "endereco": "Rua da Beleza, 789 - Vila Nova",
            "horario": "Ter a Sáb: 9h às 20h",
            "instagram": "https://instagram.com/anacabelos",
            "whatsapp": "5511777777777",
        },
    ]


# ---------------------------------------------------------------------------
# Geração de HTML
# ---------------------------------------------------------------------------

CSS = """
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
  background: #f5f5f5;
  color: #333;
  line-height: 1.6;
}

.container {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
}

/* Header */
.header {
  background: #2563eb;
  color: #fff;
  padding: 30px 20px;
  text-align: center;
}

.header h1 {
  font-size: 1.8rem;
  margin-bottom: 5px;
}

.header p {
  font-size: 0.95rem;
  opacity: 0.9;
}

/* Search / Filter */
.search-bar {
  background: #fff;
  padding: 15px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.search-bar .container {
  padding: 0;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.search-input {
  flex: 1;
  min-width: 200px;
  padding: 10px 15px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: #2563eb;
}

.filter-select {
  padding: 10px 15px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  outline: none;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.2s;
}

.filter-select:focus {
  border-color: #2563eb;
}

/* Lista de serviços */
.service-list {
  list-style: none;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  margin-top: 20px;
}

.service-item {
  display: flex;
  align-items: center;
  padding: 18px 20px;
  border-bottom: 1px solid #f0f0f0;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s ease;
  cursor: pointer;
}

.service-item:last-child {
  border-bottom: none;
}

.service-item:hover {
  background: #eff6ff;
}

.service-item-content {
  flex: 1;
  min-width: 0;
}

.service-item-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 2px;
}

.service-item-category {
  display: inline-block;
  font-size: 0.8rem;
  font-weight: 600;
  color: #2563eb;
  background: #eff6ff;
  padding: 2px 10px;
  border-radius: 20px;
  margin-bottom: 5px;
}

.service-item-desc {
  font-size: 0.9rem;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-item-arrow {
  color: #ccc;
  font-size: 1.2rem;
  margin-left: 15px;
  flex-shrink: 0;
}

.no-results {
  text-align: center;
  padding: 40px 20px;
  color: #999;
  font-size: 1rem;
  display: none;
}

/* Página de detalhes - Card */
.detail-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  padding: 30px;
  margin-top: 20px;
}

.detail-header {
  margin-bottom: 25px;
  padding-bottom: 20px;
  border-bottom: 2px solid #f0f0f0;
}

.detail-name {
  font-size: 1.6rem;
  font-weight: 700;
  color: #1a1a1a;
  margin-bottom: 8px;
}

.detail-category {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 600;
  color: #2563eb;
  background: #eff6ff;
  padding: 4px 14px;
  border-radius: 20px;
}

.detail-section {
  margin-bottom: 18px;
}

.detail-label {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #999;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 1rem;
  color: #333;
}

.detail-value a {
  color: #2563eb;
  text-decoration: none;
}

.detail-value a:hover {
  text-decoration: underline;
}

.detail-desc {
  font-size: 1rem;
  color: #444;
  line-height: 1.7;
}

/* Redes sociais */
.social-icons {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 2px solid #f0f0f0;
}

.social-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  font-size: 1.3rem;
  color: #fff;
  text-decoration: none;
  transition: opacity 0.2s, transform 0.2s;
}

.social-icon:hover {
  opacity: 0.85;
  transform: scale(1.05);
}

.social-icon.instagram {
  background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
}

.social-icon.whatsapp {
  background: #25d366;
}

/* Botão voltar */
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #fff;
  color: #2563eb;
  text-decoration: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.95rem;
  border: 2px solid #2563eb;
  transition: background 0.2s, color 0.2s;
}

.back-btn:hover {
  background: #2563eb;
  color: #fff;
}

/* Footer */
.footer {
  text-align: center;
  padding: 30px 20px;
  color: #999;
  font-size: 0.85rem;
}

/* Responsivo */
@media (max-width: 600px) {
  .header h1 {
    font-size: 1.4rem;
  }

  .container {
    padding: 15px;
  }

  .service-item {
    padding: 15px;
  }

  .service-item-name {
    font-size: 1rem;
  }

  .service-item-desc {
    white-space: normal;
  }

  .detail-card {
    padding: 20px;
  }

  .detail-name {
    font-size: 1.3rem;
  }

  .search-bar .container {
    flex-direction: column;
  }

  .search-input, .filter-select {
    width: 100%;
  }
}
"""


def generate_index_html(services: list) -> str:
    """Gera o HTML da página inicial com lista de serviços."""
    categories = sorted(set(s["categoria"] for s in services if s["categoria"]))

    items_html = []
    for s in services:
        slug = s["_slug"]
        name = esc(s["nome"])
        category = esc(s["categoria"])
        desc_short = esc(truncate(s["descricao"], 80))
        items_html.append(f"""        <li class="service-item" data-name="{name.lower()}" data-category="{category.lower()}">
          <a href="services/{slug}/" style="text-decoration:none;color:inherit;display:flex;align-items:center;width:100%">
            <div class="service-item-content">
              <div class="service-item-name">{name}</div>
              <span class="service-item-category">{category}</span>
              <div class="service-item-desc">{desc_short}</div>
            </div>
            <span class="service-item-arrow"><i class="fas fa-chevron-right"></i></span>
          </a>
        </li>""")

    items = "\n".join(items_html)

    category_options = "\n".join(
        f'<option value="{esc(cat)}">{esc(cat)}</option>' for cat in categories
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Catálogo UP - Serviços</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
{CSS}
  </style>
</head>
<body>
  <div class="header">
    <h1><i class="fas fa-tools"></i> Catálogo UP</h1>
    <p>Encontre os melhores serviços da sua região</p>
  </div>

  <div class="search-bar">
    <div class="container">
      <input type="text" class="search-input" id="searchInput" placeholder="Buscar serviço...">
      <select class="filter-select" id="categoryFilter">
        <option value="">Todas as categorias</option>
        {category_options}
      </select>
    </div>
  </div>

  <div class="container">
    <ul class="service-list" id="serviceList">
{items}
    </ul>
    <div class="no-results" id="noResults">
      <i class="fas fa-search" style="font-size:2rem;margin-bottom:10px"></i>
      <p>Nenhum serviço encontrado.</p>
    </div>
  </div>

  <div class="footer">
    <p>Catálogo UP &copy; 2025</p>
  </div>

  <script>
    (function() {{
      var searchInput = document.getElementById('searchInput');
      var categoryFilter = document.getElementById('categoryFilter');
      var items = document.querySelectorAll('.service-item');
      var noResults = document.getElementById('noResults');

      function filter() {{
        var query = searchInput.value.toLowerCase().trim();
        var cat = categoryFilter.value.toLowerCase().trim();
        var visible = 0;
        items.forEach(function(item) {{
          var name = item.getAttribute('data-name') || '';
          var category = item.getAttribute('data-category') || '';
          var matchName = name.indexOf(query) !== -1;
          var matchCat = !cat || category === cat;
          if (matchName && matchCat) {{
            item.style.display = '';
            visible++;
          }} else {{
            item.style.display = 'none';
          }}
        }});
        noResults.style.display = visible === 0 ? 'block' : 'none';
      }}

      searchInput.addEventListener('input', filter);
      categoryFilter.addEventListener('change', filter);
    }})();
  </script>
</body>
</html>"""


def generate_detail_html(service: dict) -> str:
    """Gera o HTML da página de detalhes de um serviço em card."""
    name = esc(service["nome"])
    category = esc(service["categoria"])
    desc = esc(service["descricao"])
    phone = esc(service["telefone"])
    email = esc(service["email"])
    address = esc(service["endereco"])
    hours = esc(service["horario"])
    instagram = service.get("instagram", "")
    whatsapp = service.get("whatsapp", "")

    # Seção descrição
    desc_html = f"""    <div class="detail-section">
      <div class="detail-label">Descrição</div>
      <div class="detail-desc">{desc}</div>
    </div>""" if desc else ""

    # Seção telefone
    phone_html = f"""    <div class="detail-section">
      <div class="detail-label"><i class="fas fa-phone"></i> Telefone</div>
      <div class="detail-value">{phone}</div>
    </div>""" if phone else ""

    # Seção email
    email_html = f"""    <div class="detail-section">
      <div class="detail-label"><i class="fas fa-envelope"></i> E-mail</div>
      <div class="detail-value"><a href="mailto:{email}">{email}</a></div>
    </div>""" if email else ""

    # Seção endereço
    address_html = f"""    <div class="detail-section">
      <div class="detail-label"><i class="fas fa-map-marker-alt"></i> Endereço</div>
      <div class="detail-value">{address}</div>
    </div>""" if address else ""

    # Seção horário
    hours_html = f"""    <div class="detail-section">
      <div class="detail-label"><i class="fas fa-clock"></i> Horário de Funcionamento</div>
      <div class="detail-value">{hours}</div>
    </div>""" if hours else ""

    # Ícones sociais
    social_icons = []
    if instagram:
        ig_url = instagram if instagram.startswith("http") else f"https://instagram.com/{instagram.replace('@', '')}"
        social_icons.append(
            f'<a href="{esc(ig_url)}" target="_blank" rel="noopener noreferrer" class="social-icon instagram" title="Instagram"><i class="fab fa-instagram"></i></a>'
        )
    if whatsapp:
        wa_num = re.sub(r"\D", "", whatsapp)
        social_icons.append(
            f'<a href="https://wa.me/{wa_num}" target="_blank" rel="noopener noreferrer" class="social-icon whatsapp" title="WhatsApp"><i class="fab fa-whatsapp"></i></a>'
        )

    social_html = f"""    <div class="social-icons">
      {''.join(social_icons)}
    </div>""" if social_icons else ""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name} - Catálogo UP</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
{CSS}
  </style>
</head>
<body>
  <div class="header">
    <h1><i class="fas fa-tools"></i> Catálogo UP</h1>
    <p>Detalhes do serviço</p>
  </div>

  <div class="container">
    <a href="../../" class="back-btn">
      <i class="fas fa-arrow-left"></i> Voltar à lista
    </a>

    <div class="detail-card">
      <div class="detail-header">
        <div class="detail-name">{name}</div>
        <span class="detail-category">{category}</span>
      </div>

{desc_html}
{phone_html}
{email_html}
{address_html}
{hours_html}
{social_html}
    </div>
  </div>

  <div class="footer">
    <p>Catálogo UP &copy; 2025</p>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Build principal
# ---------------------------------------------------------------------------

def clean_public_dir():
    """Limpa o diretório public para regenerar."""
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def build():
    """Função principal de build."""
    print("[Catálogo UP] Iniciando build...")

    # Lê dados
    services = read_google_sheets()
    if not services:
        print("[Catálogo UP] Nenhum serviço encontrado. Build vazio.")
        services = get_sample_data()

    # Gera slugs únicos
    existing_slugs = set()
    for s in services:
        base_slug = slugify(s.get("nome", "servico"))
        s["_slug"] = ensure_unique_slug(base_slug, existing_slugs)

    # Limpa e recria public
    clean_public_dir()

    # Gera página inicial (lista)
    index_html = generate_index_html(services)
    index_path = PUBLIC_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"[Catálogo UP] Página inicial gerada: {index_path}")

    # Gera páginas de detalhes
    for s in services:
        slug = s["_slug"]
        service_dir = SERVICES_DIR / slug
        service_dir.mkdir(parents=True, exist_ok=True)

        detail_html = generate_detail_html(s)
        detail_path = service_dir / "index.html"
        detail_path.write_text(detail_html, encoding="utf-8")
        print(f"[Catálogo UP] Detalhe gerado: {detail_path}")

    # Gera dados JSON para uso opcional
    json_path = ASSETS_DIR / "services.json"
    json_data = []
    for s in services:
        json_data.append({
            "slug": s["_slug"],
            "nome": s["nome"],
            "categoria": s["categoria"],
            "descricao": s["descricao"],
            "telefone": s["telefone"],
            "email": s["email"],
            "endereco": s["endereco"],
            "horario": s["horario"],
            "instagram": s.get("instagram", ""),
            "whatsapp": s.get("whatsapp", ""),
        })
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Catálogo UP] JSON gerado: {json_path}")

    print(f"[Catálogo UP] Build concluído! {len(services)} serviços publicados.")


if __name__ == "__main__":
    build()