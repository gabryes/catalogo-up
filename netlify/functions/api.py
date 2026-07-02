import json
import os
import logging
from flask import Flask, jsonify, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Fallback data extracted from the static site constants
FALLBACK_SERVICES = [
    {
        "id": 1,
        "title": "Criação de Sites Profissionais",
        "category": "tecnologia",
        "subcategory": "Desenvolvimento Web",
        "premium": True,
        "price": "A partir de R$ 1.200",
        "rating": 4.9,
        "description": "Sites modernos, responsivos e otimizados para SEO. Do landing page ao e-commerce.",
        "phone": "11999990001",
        "whatsapp": "11999990001",
        "email": "dev1@exemplo.com",
        "instagram": "web_exemplo"
    },
    {
        "id": 2,
        "title": "Suporte Técnico Remoto",
        "category": "tecnologia",
        "subcategory": "Suporte Técnico",
        "premium": False,
        "price": "R$ 80/hora",
        "rating": 4.7,
        "description": "Resolução de problemas de software, instalação de programas e remoção de vírus.",
        "phone": "11999990002",
        "whatsapp": "11999990002",
        "email": "suporte@exemplo.com",
        "instagram": "tech_suporte"
    },
    {
        "id": 3,
        "title": "Consultoria em Segurança da Informação",
        "category": "tecnologia",
        "subcategory": "Consultoria em TI",
        "premium": True,
        "price": "Sob consulta",
        "rating": 4.8,
        "description": "Análise de vulnerabilidades, políticas de segurança e treinamento para equipes.",
        "phone": "11999990003",
        "whatsapp": "11999990003",
        "email": "seguranca@exemplo.com",
        "instagram": "cyber_exemplo"
    },
    {
        "id": 4,
        "title": "Instalação de Redes Wi-Fi Mesh",
        "category": "tecnologia",
        "subcategory": "Redes e Wi-Fi",
        "premium": False,
        "price": "R$ 350",
        "rating": 4.6,
        "description": "Configuração de roteadores e extensores para cobertura total em casa ou empresa.",
        "phone": "11999990004",
        "whatsapp": "11999990004",
        "email": "redes@exemplo.com",
        "instagram": "wifi_pro"
    },
    {
        "id": 5,
        "title": "Identidade Visual Completa",
        "category": "design",
        "subcategory": "Identidade Visual",
        "premium": True,
        "price": "A partir de R$ 900",
        "rating": 4.9,
        "description": "Logo, paleta de cores, tipografia e manual de marca para o seu negócio.",
        "phone": "11999990005",
        "whatsapp": "11999990005",
        "email": "marca@exemplo.com",
        "instagram": "design_marca"
    },
    {
        "id": 6,
        "title": "Prototipagem de Interfaces",
        "category": "design",
        "subcategory": "UI/UX Design",
        "premium": False,
        "price": "R$ 150/tela",
        "rating": 4.7,
        "description": "Wireframes e protótipos navegáveis para validar ideias antes do desenvolvimento.",
        "phone": "11999990006",
        "whatsapp": "11999990006",
        "email": "ux@exemplo.com",
        "instagram": "ux_exemplo"
    },
    {
        "id": 7,
        "title": "Animação de Vídeos Promocionais",
        "category": "design",
        "subcategory": "Motion Graphics",
        "premium": True,
        "price": "A partir de R$ 1.500",
        "rating": 4.8,
        "description": "Vídeos animados para redes sociais, apresentações e campanhas publicitárias.",
        "phone": "11999990007",
        "whatsapp": "11999990007",
        "email": "motion@exemplo.com",
        "instagram": "motion_studio"
    },
    {
        "id": 8,
        "title": "Ilustrações Personalizadas",
        "category": "design",
        "subcategory": "Ilustração",
        "premium": False,
        "price": "R$ 200/ilustração",
        "rating": 4.8,
        "description": "Ilustrações digitais exclusivas para presentes, livros e conteúdo de marca.",
        "phone": "11999990008",
        "whatsapp": "11999990008",
        "email": "arte@exemplo.com",
        "instagram": "ilustra_art"
    },
    {
        "id": 9,
        "title": "Fisioterapia Domiciliar",
        "category": "saude",
        "subcategory": "Fisioterapia",
        "premium": False,
        "price": "R$ 180/hora",
        "rating": 4.9,
        "description": "Atendimento de fisioterapia no conforto da sua casa, com plano personalizado.",
        "phone": "11999990009",
        "whatsapp": "11999990009",
        "email": "fisio@exemplo.com",
        "instagram": "fisio_casa"
    },
    {
        "id": 10,
        "title": "Consultoria Nutricional Online",
        "category": "saude",
        "subcategory": "Nutrição",
        "premium": True,
        "price": "R$ 250/mês",
        "rating": 4.8,
        "description": "Planos alimentares individualizados e acompanhamento semanal por vídeo.",
        "phone": "11999990010",
        "whatsapp": "11999990010",
        "email": "nutri@exemplo.com",
        "instagram": "nutri_vida"
    },
    {
        "id": 11,
        "title": "Personal Trainer ao Ar Livre",
        "category": "saude",
        "subcategory": "Personal Trainer",
        "premium": False,
        "price": "R$ 120/aula",
        "rating": 4.7,
        "description": "Treinos funcionais em parques e praças, adaptados ao seu nível físico.",
        "phone": "11999990011",
        "whatsapp": "11999990011",
        "email": "treino@exemplo.com",
        "instagram": "personal_fit"
    },
    {
        "id": 12,
        "title": "Psicoterapia Online",
        "category": "saude",
        "subcategory": "Psicologia",
        "premium": True,
        "price": "R$ 200/hora",
        "rating": 4.9,
        "description": "Sessões de psicoterapia por vídeo com agendamento flexível e sigilo profissional.",
        "phone": "11999990012",
        "whatsapp": "11999990012",
        "email": "psi@exemplo.com",
        "instagram": "psi_online"
    },
    {
        "id": 13,
        "title": "Reforma de Apartamentos",
        "category": "casa",
        "subcategory": "Reformas",
        "premium": True,
        "price": "Sob orçamento",
        "rating": 4.6,
        "description": "Reformas integrais, pintura, revestimentos e acabamentos de qualidade.",
        "phone": "11999990013",
        "whatsapp": "11999990013",
        "email": "reforma@exemplo.com",
        "instagram": "reforma_total"
    },
    {
        "id": 14,
        "title": "Instalação Elétrica Residencial",
        "category": "casa",
        "subcategory": "Elétrica",
        "premium": False,
        "price": "R$ 280",
        "rating": 4.7,
        "description": "Instalação de tomadas, lustres, quadros de distribuição e revisões elétricas.",
        "phone": "11999990014",
        "whatsapp": "11999990014",
        "email": "eletrica@exemplo.com",
        "instagram": "eletrica_pro"
    },
    {
        "id": 15,
        "title": "Encanador 24 Horas",
        "category": "casa",
        "subcategory": "Hidráulica",
        "premium": False,
        "price": "R$ 180",
        "rating": 4.5,
        "description": "Desentupimento, reparos em torneiras, instalação de louças e caixa d’água.",
        "phone": "11999990015",
        "whatsapp": "11999990015",
        "email": "encanador@exemplo.com",
        "instagram": "hidro_rapido"
    },
    {
        "id": 16,
        "title": "Jardinagem e Paisagismo",
        "category": "casa",
        "subcategory": "Jardinagem",
        "premium": True,
        "price": "A partir de R$ 300",
        "rating": 4.8,
        "description": "Projeto e manutenção de jardins, podas, plantio e irrigação.",
        "phone": "11999990016",
        "whatsapp": "11999990016",
        "email": "jardim@exemplo.com",
        "instagram": "jardim_lindo"
    },
    {
        "id": 17,
        "title": "Fotografia de Eventos",
        "category": "eventos",
        "subcategory": "Fotografia",
        "premium": True,
        "price": "A partir de R$ 1.800",
        "rating": 4.9,
        "description": "Cobertura fotográfica de festas, casamentos e eventos corporativos.",
        "phone": "11999990017",
        "whatsapp": "11999990017",
        "email": "foto@exemplo.com",
        "instagram": "foto_eventos"
    },
    {
        "id": 18,
        "title": "Filmagem e Edição de Vídeo",
        "category": "eventos",
        "subcategory": "Filmagem",
        "premium": False,
        "price": "R$ 900/evento",
        "rating": 4.7,
        "description": "Captura e edição profissional de vídeos para eventos e produtos.",
        "phone": "11999990018",
        "whatsapp": "11999990018",
        "email": "video@exemplo.com",
        "instagram": "video_prod"
    },
    {
        "id": 19,
        "title": "DJ para Festas e Eventos",
        "category": "eventos",
        "subcategory": "DJ e Som",
        "premium": True,
        "price": "R$ 1.200/noite",
        "rating": 4.8,
        "description": "Som, iluminação e playlist personalizada para festas de todos os tamanhos.",
        "phone": "11999990019",
        "whatsapp": "11999990019",
        "email": "dj@exemplo.com",
        "instagram": "dj_festa"
    },
    {
        "id": 20,
        "title": "Buffet para Festas",
        "category": "eventos",
        "subcategory": "Buffet",
        "premium": False,
        "price": "R$ 60/pessoa",
        "rating": 4.6,
        "description": "Cardápios variados com entrada, pratos principais e sobremesas para eventos.",
        "phone": "11999990020",
        "whatsapp": "11999990020",
        "email": "buffet@exemplo.com",
        "instagram": "buffet_festas"
    }
]

FALLBACK_CATEGORIES = [
    {
        "id": "tecnologia",
        "name": "Tecnologia",
        "icon": "💻",
        "subcategories": ["Desenvolvimento Web", "Suporte Técnico", "Redes e Wi-Fi", "Consultoria em TI"]
    },
    {
        "id": "design",
        "name": "Design & Criativo",
        "icon": "🎨",
        "subcategories": ["Identidade Visual", "UI/UX Design", "Motion Graphics", "Ilustração"]
    },
    {
        "id": "saude",
        "name": "Saúde & Bem-estar",
        "icon": "🩺",
        "subcategories": ["Fisioterapia", "Nutrição", "Personal Trainer", "Psicologia"]
    },
    {
        "id": "casa",
        "name": "Casa & Construção",
        "icon": "🏠",
        "subcategories": ["Reformas", "Elétrica", "Hidráulica", "Jardinagem"]
    },
    {
        "id": "eventos",
        "name": "Eventos & Entretenimento",
        "icon": "🎉",
        "subcategories": ["Fotografia", "Filmagem", "DJ e Som", "Buffet"]
    },
    {
        "id": "automotivo",
        "name": "Automotivo",
        "icon": "🚗",
        "subcategories": ["Mecânica", "Funilaria", "Estética Automotiva", "Vistoria"]
    }
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Google Sheets configuration
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
SHEETS_KEY = os.environ.get('GOOGLE_SHEETS_KEY')


def get_gsheet_client():
    """Connect to Google Sheets using service account credentials."""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error("Google Sheets auth failed: %s", e)
        return None


def get_sheet_data(sheet_name):
    """Fetch all records from a specific sheet. Returns list of dicts or None on failure."""
    client = get_gsheet_client()
    if not client:
        return None
    try:
        sheet = client.open_by_key(SHEETS_KEY).worksheet(sheet_name)
        records = sheet.get_all_records()
        return records
    except Exception as e:
        logger.error("Failed to get sheet '%s': %s", sheet_name, e)
        return None


def fetch_services():
    """Get services from Google Sheets or fallback to local data."""
    data = get_sheet_data('services')
    if data is None or len(data) == 0:
        logger.info("Using fallback services data")
        return FALLBACK_SERVICES
    return data


def fetch_categories():
    """Get categories from Google Sheets or fallback to local data."""
    data = get_sheet_data('categories')
    if data is None or len(data) == 0:
        logger.info("Using fallback categories data")
        return FALLBACK_CATEGORIES
    return data


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return response


@app.route('/api/hello')
def hello():
    return jsonify({"message": "Hello from Guia de Serviços API!"})


@app.route('/api/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/api/env')
def env():
    # Show environment variables, excluding sensitive ones
    safe_env = {}
    for key, value in os.environ.items():
        lower = key.lower()
        if any(secret in lower for secret in ['key', 'secret', 'token', 'password', 'auth']):
            safe_env[key] = '***REDACTED***'
        else:
            safe_env[key] = value
    return jsonify(safe_env)


@app.route('/api/services')
def services():
    category = request.args.get('category')
    all_services = fetch_services()
    if category:
        all_services = [s for s in all_services if s.get('category') == category]
    return jsonify(all_services)


@app.route('/api/categories')
def categories():
    return jsonify(fetch_categories())


def handler(event, context):
    """Netlify Function entry point for serverless-wsgi."""
    from serverless_wsgi import handle_request
    return handle_request(app, event, context)


if __name__ == '__main__':
    app.run(debug=True)