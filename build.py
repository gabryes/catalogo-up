#!/usr/bin/env python3
"""
build.py - Catálogo UP
Gera um site estático a partir de dados de uma planilha Google Sheets.
"""

import base64
import json
import os
import re
import sys
import shutil
from pathlib import Path

try:
    import gspread
except ImportError:
    print("[Catálogo UP] ERRO: O pacote 'gspread' não está instalado.")
    print("               Instale com: pip install gspread")
    sys.exit(1)

# Configurações
BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

COBERTA_AZUL = "#0055D4"
AZUL_MARINHO = "#0B1E40"

COLUNAS_ESPERADAS = [
    "id", "nome", "categoria", "responsavel", "telefone",
    "whatsapp", "email", "endereco", "horario", "descricao", "instagram", "foto_logo_url", "publicidade",
]

# Funções auxiliares
def slugify(texto: str) -> str:
    texto = (texto or "").strip().lower()
    texto = re.sub(r"[áàâãä]", "a", texto)
    texto = re.sub(r"[éèêë]", "e", texto)
    texto = re.sub(r"[íìîï]", "i", texto)
    texto = re.sub(r"[óòôõö]", "o", texto)
    texto = re.sub(r"[úùûü]", "u", texto)
    texto = re.sub(r"ç", "c", texto)
    texto = re.sub(r"ñ", "n", texto)
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = re.sub(r"^-+|-+$", "", texto)
    return texto or "servico"

def escapa_html(texto: str) -> str:
    if texto is None:
        return ""
    texto = str(texto)
    return (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def garantir_unicos_slugs(servicos):
    usados = set()
    for s in servicos:
        base = slugify(s.get("nome", "servico"))
        slug = base
        i = 1
        while slug in usados:
            slug = f"{base}-{i}"
            i += 1
        usados.add(slug)
        s["id"] = slug
    return servicos

# CSS e Templates
def css_base() -> str:
    return f"""
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: {AZUL_MARINHO};
      background: #f5f7fb;
      line-height: 1.6;
    }}
    header {{
      background: {AZUL_MARINHO};
      color: #fff;
      padding: 1.5rem 1rem;
      text-align: center;
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    header h1 a {{ color: #fff; text-decoration: none; }}
    header p {{ opacity: 0.8; margin-top: 0.3rem; font-size: 0.95rem; }}
    main {{ max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    .barra-busca {{
      display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.5rem;
    }}
    .barra-busca input[type="text"],
    .barra-busca select {{
      padding: 0.7rem 0.9rem; border: 1px solid #d0d7e2; border-radius: 8px;
      font-size: 1rem; background: #fff; color: {AZUL_MARINHO};
    }}
    .barra-busca input[type="text"] {{ flex: 1 1 260px; }}
    .barra-busca select {{ flex: 0 1 220px; }}
    .barra-busca input:focus, .barra-busca select:focus {{
      outline: none; border-color: {COBERTA_AZUL};
      box-shadow: 0 0 0 3px rgba(0,85,212,0.15);
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }}
    .card {{
      background: #fff; border-radius: 10px; padding: 1.2rem;
      box-shadow: 0 1px 3px rgba(11,30,64,0.08);
      border: 1px solid #e6ebf2; display: flex; flex-direction: column;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,85,212,0.18); }}
    .card h3 {{ color: {COBERTA_AZUL}; font-size: 1.1rem; margin-bottom: 0.4rem; }}
    .card .categoria {{
      display: inline-block; font-size: 0.75rem; font-weight: 600;
      background: rgba(0,85,212,0.1); color: {COBERTA_AZUL};
      padding: 0.2rem 0.6rem; border-radius: 999px; margin-bottom: 0.6rem;
      align-self: flex-start;
    }}
    .card .descricao {{ color: #4a5878; font-size: 0.9rem; flex: 1; }}
    .card a.ver {{
      margin-top: 0.9rem; color: {COBERTA_AZUL}; text-decoration: none;
      font-weight: 600; font-size: 0.9rem;
    }}
    .card a.ver:hover {{ text-decoration: underline; }}
    .detalhe {{ background: #fff; border-radius: 12px; padding: 2rem; box-shadow: 0 1px 3px rgba(11,30,64,0.08); }}
    .detalhe h2 {{ color: {COBERTA_AZUL}; margin-bottom: 0.5rem; }}
    .detalhe .categoria {{
      display: inline-block; font-size: 0.8rem; font-weight: 600;
      background: rgba(0,85,212,0.1); color: {COBERTA_AZUL};
      padding: 0.25rem 0.7rem; border-radius: 999px; margin-bottom: 1rem;
    }}
    .detalhe .descricao {{ margin-bottom: 1.5rem; color: #33415c; }}
    .detalhe .info {{ display: grid; grid-template-columns: 1fr; gap: 0.8rem; }}
    .detalhe .info-item {{ border-top: 1px solid #eef2f7; padding-top: 0.6rem; }}
    .detalhe .info-item .rotulo {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: #8a98b3; }}
    .detalhe .info-item .valor {{ color: {AZUL_MARINHO}; }}
    .detalhe .info-item a {{ color: {COBERTA_AZUL}; text-decoration: none; }}
    .detalhe .info-item a:hover {{ text-decoration: underline; }}
    .voltar {{ display: inline-block; margin-bottom: 1rem; color: {COBERTA_AZUL}; text-decoration: none; font-weight: 600; }}
    .voltar:hover {{ text-decoration: underline; }}
    .vazio {{ text-align: center; color: #8a98b3; padding: 2rem; }}
    footer {{ text-align: center; padding: 2rem 1rem; color: #8a98b3; font-size: 0.85rem; }}
    .btn {{
      display: inline-block; background: {COBERTA_AZUL}; color: #fff;
      padding: 0.6rem 1.2rem; border-radius: 8px; text-decoration: none;
      font-weight: 600; margin-top: 1rem;
    }}
    .btn:hover {{ background: {AZUL_MARINHO}; }}
    .social-icons {{
      display: flex; gap: 1rem; margin-top: 1.5rem;
    }}
    .social-whatsapp, .social-instagram, .social-telefone {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 40px; height: 40px; border-radius: 50%;
      color: white; text-decoration: none;
    }}
    .social-whatsapp {{ background-color: #25D366; }}
    .social-whatsapp svg {{
      width: 24px; height: 24px;
      display: block; margin: auto;
    }}
    .social-instagram {{ background-color: #E1306C; }}
    .social-telefone {{ background-color: #6c757d; }}
    """

def cabecalho_html(titulo: str, prefix: str, subtitulo: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escapa_html(titulo)} | Catálogo UP</title>
<style>{css_base()}</style>
</head>
<body>
<header>
  <h1><a href="{prefix}index.html">Catálogo UP</a></h1>
  {f'<p>{escapa_html(subtitulo)}</p>' if subtitulo else '<p>Serviços da comunidade universitária</p>'}
</header>
<main>
"""

def rodape_html() -> str:
    return """
</main>
<footer>
  Catálogo UP &middot; Gerado automaticamente a partir do Google Sheets
</footer>
</body>
</html>
"""

# Geração de páginas
def gerar_home(servicos, categorias):
    prefix = ""
    dados_json = json.dumps(
        [
            {
                "id": s["id"],
                "nome": s.get("nome", ""),
                "categoria": s.get("categoria", ""),
                "descricao": s.get("descricao", ""),
            }
            for s in servicos
        ],
        ensure_ascii=False,
    )

    opcoes_cat = "\n".join(
        f'<option value="{escapa_html(c)}">{escapa_html(c)}</option>'
        for c in categorias
    )

    cards = "\n".join(
        f'''<article class="card" data-nome="{escapa_html(s.get('nome','').lower())}" data-categoria="{escapa_html(s.get('categoria',''))}">
  <span class="categoria">{escapa_html(s.get('categoria',''))}</span>
  <h3>{escapa_html(s.get('nome',''))}</h3>
  <p class="descricao">{escapa_html((s.get('descricao','') or '')[:120])}{'...' if len(s.get('descricao','') or '') > 120 else ''}</p>
  <a class="ver" href="{prefix}services/{s['id']}/index.html">Ver detalhes &rarr;</a>
</article>'''
        for s in servicos
    )

    html = cabecalho_html("Início", prefix, "Encontre o serviço que você precisa")
    html += f"""
<div class="barra-busca">
  <input type="text" id="busca" placeholder="Buscar por nome ou descrição..." autocomplete="off">
  <select id="filtro-categoria">
    <option value="">Todas as categorias</option>
    {opcoes_cat}
  </select>
</div>
<div class="grid" id="lista-servicos">
{cards}
</div>
<div class="vazio" id="sem-resultados" style="display:none;">
  Nenhum serviço encontrado para a sua busca.
</div>
<script>
const SERVICOS = {dados_json};
const busca = document.getElementById('busca');
const filtro = document.getElementById('filtro-categoria');
const lista = document.getElementById('lista-servicos');
const vazio = document.getElementById('sem-resultados');
function render() {{
  const q = busca.value.trim().toLowerCase();
  const cat = filtro.value;
  const filtrados = SERVICOS.filter(s => {{
    const matchCat = !cat || s.categoria === cat;
    const matchQ = !q || s.nome.toLowerCase().includes(q) || s.descricao.toLowerCase().includes(q);
    return matchCat && matchQ;
  }});
  lista.innerHTML = filtrados.map(s => `
    <article class="card">
      <span class="categoria">${{s.categoria}}</span>
      <h3>${{s.nome}}</h3>
      <p class="descricao">${{(s.descricao||'').slice(0,120)}}${{(s.descricao||'').length>120?'...':''}}</p>
      <a class="ver" href="services/${{s.id}}/index.html">Ver detalhes &rarr;</a>
    </article>
  `).join('');
  vazio.style.display = filtrados.length ? 'none' : 'block';
}}
busca.addEventListener('input', render);
filtro.addEventListener('change', render);
</script>
"""
    html += rodape_html()
    return html

def gerar_lista_servicos(servicos, categorias):
    prefix = "../"
    opcoes_cat = "\n".join(
        f'<option value="{escapa_html(c)}">{escapa_html(c)}</option>'
        for c in categorias
    )
    dados_json = json.dumps(
        [
            {
                "id": s["id"],
                "nome": s.get("nome", ""),
                "categoria": s.get("categoria", ""),
                "descricao": s.get("descricao", ""),
            }
            for s in servicos
        ],
        ensure_ascii=False,
    )

    html = cabecalho_html("Serviços", prefix, "Lista completa de serviços")
    html += f"""
<a class="voltar" href="{prefix}index.html">&larr; Voltar ao início</a>
<div class="barra-busca">
  <input type="text" id="busca" placeholder="Buscar serviços..." autocomplete="off">
  <select id="filtro-categoria">
    <option value="">Todas as categorias</option>
    {opcoes_cat}
  </select>
</div>
<div class="grid" id="lista-servicos"></div>
<div class="vazio" id="sem-resultados" style="display:none;">
  Nenhum serviço encontrado.
</div>
<script>
const SERVICOS = {dados_json};
const busca = document.getElementById('busca');
const filtro = document.getElementById('filtro-categoria');
const lista = document.getElementById('lista-servicos');
const vazio = document.getElementById('sem-resultados');
function render() {{
  const q = busca.value.trim().toLowerCase();
  const cat = filtro.value;
  const filtrados = SERVICOS.filter(s => {{
    const matchCat = !cat || s.categoria === cat;
    const matchQ = !q || s.nome.toLowerCase().includes(q) || s.descricao.toLowerCase().includes(q);
    return matchCat && matchQ;
  }});
  lista.innerHTML = filtrados.map(s => `
    <article class="card">
      <span class="categoria">${{s.categoria}}</span>
      <h3>${{s.nome}}</h3>
      <p class="descricao">${{(s.descricao||'').slice(0,120)}}${{(s.descricao||'').length>120?'...':''}}</p>
      <a class="ver" href="${{s.id}}/index.html">Ver detalhes &rarr;</a>
    </article>
  `).join('');
  vazio.style.display = filtrados.length ? 'none' : 'block';
}}
busca.addEventListener('input', render);
filtro.addEventListener('change', render);
render();
</script>
"""
    html += rodape_html()
    return html

def gerar_detalhe_servico(servico):
    prefix = "../../"
    nome = servico.get("nome", "Serviço")
    categoria = servico.get("categoria", "")
    descricao = servico.get("descricao", "")

    campos = [
        ("Telefone", servico.get("telefone", "")),
        ("E-mail", servico.get("email", "")),
        ("Endereço", servico.get("endereco", "")),
        ("Horário", servico.get("horario", "")),
        ("Contato", servico.get("contato", "")),
    ]

    linhas = []
    for rotulo, valor in campos:
        if valor and str(valor).strip():
            v = escapa_html(valor)
            if rotulo == "E-mail" and "@" in str(valor):
                v = f'<a href="mailto:{escapa_html(valor)}">{escapa_html(valor)}</a>'
            if rotulo == "Telefone":
                tel = re.sub(r"[^0-9+]", "", str(valor))
                v = f'<a href="tel:{tel}">{escapa_html(valor)}</a>'
            linhas.append(
                f'<div class="info-item"><div class="rotulo">{rotulo}</div>'
                f'<div class="valor">{v}</div></div>'
            )

    # Construir ícones de contato inline (SVG) substituindo Font Awesome
    icones_contato = []
    
    # WhatsApp
    whatsapp = servico.get("whatsapp", "").strip()
    if whatsapp:
        numero_limpo = re.sub(r'[^0-9]', '', whatsapp)
        icones_contato.append(
            f'''            <a href="https://wa.me/{numero_limpo}" target="_blank" rel="noopener" class="social-whatsapp" aria-label="WhatsApp">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12.01 2.01c-5.52 0-10 4.48-10 10 0 1.75.46 3.4 1.26 4.83L2 22l5.3-.1.13.07c1.33.71 2.85 1.1 4.44 1.1 5.52 0 10-4.48 10-10s-4.48-10-10-10zm0 18.39c-1.57 0-3.1-.42-4.43-1.21l-.32-.19-3.14.06.06-3.07-.21-.33c-.87-1.38-1.33-2.98-1.33-4.63 0-4.63 3.77-8.4 8.4-8.4s8.4 3.77 8.4 8.4-3.77 8.4-8.4 8.4zm4.75-6.37c-.26-.13-1.54-.76-1.78-.85-.24-.09-.41-.13-.58.13-.17.26-.66.85-.81 1.02-.15.17-.31.19-.57.06-.26-.13-1.1-.4-2.1-1.29-.77-.69-1.29-1.54-1.44-1.8-.15-.26-.02-.4.11-.53.12-.12.26-.31.39-.46.13-.15.17-.26.26-.43.09-.17.04-.32-.02-.45-.06-.13-.58-1.39-.79-1.91-.21-.51-.42-.44-.58-.45-.15-.01-.32-.01-.49-.01-.17 0-.45.06-.68.31-.23.25-.89.87-.89 2.12 0 1.25.91 2.46 1.03 2.63.13.17 1.79 2.73 4.33 3.83.6.26 1.08.42 1.44.54.61.19 1.16.16 1.6.1.49-.07 1.54-.63 1.76-1.24.22-.61.22-1.13.15-1.24-.07-.11-.26-.17-.52-.3z"/>
              </svg>
            </a>'''
        )

    # Instagram
    instagram = servico.get("instagram", "").strip()
    if instagram:
        # Remove @ se existir e espaços
        user = instagram.lstrip('@')
        icones_contato.append(
            f'''            <a href="https://instagram.com/{escapa_html(user)}" target="_blank" rel="noopener" class="social-instagram" aria-label="Instagram">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
              </svg>
            </a>'''
        )

    # Telefone
    telefone = servico.get("telefone", "").strip()
    if telefone:
        tel_limpo = re.sub(r'[^0-9+]', '', telefone)
        icones_contato.append(
            f'''            <a href="tel:{tel_limpo}" class="social-telefone" aria-label="Telefone">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
              </svg>
            </a>'''
        )

    icones_html = ""
    if icones_contato:
        icones_html = '<div class="social-icons">\n' + "\n".join(icones_contato) + "\n        </div>"

    link_html = ""
    if servico.get("link") and str(servico.get("link")).strip():
        link_html = f'<a class="btn" href="{escapa_html(servico["link"])}" target="_blank" rel="noopener">Acessar serviço &rarr;</a>'

    html = cabecalho_html(nome, prefix, categoria)
    html += f"""
<a class="voltar" href="{prefix}index.html">&larr; Voltar ao início</a>
<a class="voltar" href="{prefix}services/index.html" style="margin-left:1rem;">&larr; Todos os serviços</a>
<div class="detalhe">
  <span class="categoria">{escapa_html(categoria)}</span>
  <h2>{escapa_html(nome)}</h2>
  <p class="descricao">{escapa_html(descricao)}</p>
  <div class="info">
    {''.join(linhas)}
  </div>
  {icones_html}
  {link_html}
</div>
"""
    html += rodape_html()
    return html

# Leitura de dados
def obter_caminho_credenciais() -> str:
    # Tenta usar variável de ambiente com base64
    creds_base64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_base64:
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        creds_path = BASE_DIR / "credentials_temp.json"
        creds_path.write_text(creds_json, encoding='utf-8')
        return str(creds_path)
    
    # Tenta arquivo local
    env_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    local = BASE_DIR / "credentials.json"
    if local.exists():
        return str(local)

    raise FileNotFoundError(
        "Credenciais do Google não encontradas.\\n"
        "Defina a variável de ambiente GOOGLE_CREDENTIALS_BASE64 (Netlify) "
        "ou coloque o arquivo credentials.json no diretório do projeto."
    )

def ler_planilha():
    print("[Catálogo UP] Lendo dados do Google Sheets...")

    # Aceita tanto GOOGLE_SHEETS_KEY quanto GOOGLE_SHEETS_ID
    sheet_key = os.environ.get("GOOGLE_SHEETS_KEY") or os.environ.get("GOOGLE_SHEETS_ID")
    if not sheet_key:
        raise EnvironmentError(
            "Variável de ambiente GOOGLE_SHEETS_KEY ou GOOGLE_SHEETS_ID não definida. "
            "Defina-a com o ID da planilha."
        )

    cred_path = obter_caminho_credenciais()

    try:
        gc = gspread.service_account(filename=cred_path)
    except Exception as e:
        raise RuntimeError(f"Não foi possível autenticar no Google Sheets: {e}")

    try:
        planilha = gc.open_by_key(sheet_key)
    except Exception as e:
        raise RuntimeError(f"Não foi possível abrir a planilha (ID: {sheet_key}): {e}")

    try:
        worksheet = planilha.worksheet("catalogo up")
    except Exception as e:
        raise RuntimeError(f"Não foi possível acessar a primeira aba da planilha: {e}")

    if worksheet is None:
        raise RuntimeError("A planilha não possui nenhuma aba disponível.")

    try:
        registros = worksheet.get_all_records()
    except Exception as e:
        raise RuntimeError(f"Erro ao ler os registros da planilha: {e}")

    # DEBUG ADICIONADO AQUI
    if registros:
        print(f"DEBUG: Nomes exatos das colunas encontradas: {list(registros[0].keys())}")
        print(f"DEBUG: Exemplo do primeiro registro: {registros[0]}")
    else:
        print("DEBUG: A planilha parece estar vazia ou não foi possível ler os registros.")

    servicos = []
    for idx, linha in enumerate(registros, start=2):
        linha_norm = {str(k).strip().lower(): v for k, v in linha.items()}

        if not any(str(v).strip() for v in linha_norm.values() if v is not None):
            continue

        servico = {}
        for col in COLUNAS_ESPERADAS:
            servico[col] = str(linha_norm.get(col, "") or "").strip()

        if not servico["nome"]:
            print(f"  [aviso] Linha {idx} ignorada por não conter 'nome'.")
            continue

        servicos.append(servico)

    servicos = garantir_unicos_slugs(servicos)
    return servicos

# Geração do site
def preparar_diretorio_publico():
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "services").mkdir(parents=True, exist_ok=True)

def escrever_arquivo(caminho: Path, conteudo: str):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")

def gerar_site(servicos):
    preparar_diretorio_publico()

    categorias = sorted({
        s.get("categoria", "") for s in servicos if s.get("categoria", "")
    })

    print(f"  -> {len(servicos)} serviços")
    print(f"  -> {len(categorias)} categorias")

    escrever_arquivo(PUBLIC_DIR / "index.html", gerar_home(servicos, categorias))
    escrever_arquivo(
        PUBLIC_DIR / "services" / "index.html",
        gerar_lista_servicos(servicos, categorias),
    )

    for s in servicos:
        dir_servico = PUBLIC_DIR / "services" / s["id"]
        escrever_arquivo(dir_servico / "index.html", gerar_detalhe_servico(s))

    print("[Catálogo UP] Site estático gerado com sucesso em 'public/'.")

# Principal
def main():
    try:
        servicos = ler_planilha()
        if not servicos:
            print("[Catálogo UP] AVISO: Nenhum serviço encontrado na planilha.")
            print("               Gerando site com lista vazia.")
        gerar_site(servicos)
    except FileNotFoundError as e:
        print(f"[Catálogo UP] ERRO: {e}")
        sys.exit(1)
    except EnvironmentError as e:
        print(f"[Catálogo UP] ERRO: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"[Catálogo UP] ERRO: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[Catálogo UP] ERRO inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()