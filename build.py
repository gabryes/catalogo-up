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

    sheet_key = os.environ.get("GOOGLE_SHEETS_KEY")
    if not sheet_key:
        raise EnvironmentError(
            "Variável de ambiente GOOGLE_SHEETS_KEY não definida. "
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