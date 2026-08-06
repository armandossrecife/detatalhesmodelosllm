import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# ==========================================
# 1. CARREGAR VARIÁVEIS DE AMBIENTE
# ==========================================
# Isso lê o arquivo .env e popula o os.environ
load_dotenv()

# ==========================================
# 2. CONFIGURAÇÃO DAS CHAVES E MODELOS
# ==========================================
CHAVES = {
    "gemini": os.environ.get("GEMINI_KEY"),
    "openai": os.environ.get("OPENAI_KEY"),
    "maritaca": os.environ.get("MARITACA_KEY"),
    "openrouter": os.environ.get("OPENROUTER_KEY"),
}

MODELOS = {
    "gemini": {
        "nome": "gemini-2.5-flash",
        "url_base": "https://generativelanguage.googleapis.com/v1beta",
    },
    "openai": {
        "nome": "gpt-4o",
        "url_base": "https://api.openai.com/v1",
    },
    "maritaca": {
        "nome": "sabia-4",
        "url_base": "https://chat.maritaca.ai/api",
    },
    "openrouter": {
        "nome": "qwen/qwen3.5-flash-02-23",
        "url_base": "https://openrouter.ai/api/v1",
    },
}

# ==========================================
# 2. BANCO DE DADOS ESTÁTICO (FALLBACK)
# ==========================================
# Como algumas APIs não retornam specs técnicas completas, mantemos um registro local
# baseado na documentação oficial de cada provedor.
SPECS_CONHECIDAS = {
    "gemini": {
        "Janela de Contexto": 1_048_576,
        "Saída Máxima": 65_536,
        "Arquitetura": "Transformer com Mixture-of-Experts (MoE)",
        "Multimodal": "Sim (Texto, Imagem, Áudio)",
    },
    "openai": {
        "Janela de Contexto": 128_000,
        "Saída Máxima": 16_384,
        "Arquitetura": "Transformer Omni (Multimodal nativo)",
        "Multimodal": "Sim (Texto, Imagem, Áudio)",
    },
    "maritaca": {
        "Janela de Contexto": 128_000,
        "Saída Máxima": "Variável",
        "Arquitetura": "Transformer Decoder-Only",
        "Multimodal": "Não (Apenas texto)",
    },
    "openrouter": None,  # OpenRouter retorna tudo dinamicamente, não precisa de fallback
}

# ==========================================
# 3. FUNÇÕES DE CONSULTA POR PROVEDOR
# ==========================================

def consultar_gemini(modelo, base_url, key):
    """Consulta a API do Google Gemini."""
    url = f"{base_url}/models/{modelo}"
    params = {"key": key}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    return {
        "ID": data.get("name"),
        "Descrição": data.get("description"),
        "Janela de Contexto (API)": data.get("inputTokenLimit"),
        "Saída Máxima (API)": data.get("outputTokenLimit"),
        "Temperatura Padrão": data.get("temperature"),
        "Top-P Padrão": data.get("topP"),
        "Top-K Padrão": data.get("topK"),
        "Métodos Suportados": ", ".join(data.get("supportedGenerationMethods", [])),
    }

def consultar_openai(modelo, base_url, key):
    """Consulta a API da OpenAI (metadados básicos)."""
    url = f"{base_url}/models/{modelo}"
    headers = {"Authorization": f"Bearer {key}"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    created = datetime.fromtimestamp(data.get("created", 0)).strftime("%d/%m/%Y") if data.get("created") else "N/A"
    
    return {
        "ID": data.get("id"),
        "Proprietário": data.get("owned_by"),
        "Criado em": created,
        "Tipo de Objeto": data.get("object"),
    }

def consultar_maritaca(modelo, base_url, key):
    """Consulta a API da Maritaca AI (atenção ao prefixo 'Key')."""
    url = f"{base_url}/models"
    headers = {"Authorization": f"Key {key}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    
    models_list = data if isinstance(data, list) else data.get("data", data.get("models", []))
    target = next((m for m in models_list if modelo.lower() in str(m.get("id", "")).lower()), {})
    
    return target or {"Aviso": f"Modelo '{modelo}' não retornado explicitamente pelo endpoint /models."}

def consultar_openrouter(modelo, base_url, key):
    """Consulta a API do OpenRouter (retorna specs técnicas completas)."""
    url = f"{base_url}/models"
    headers = {"Authorization": f"Bearer {key}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    target = next((m for m in data.get("data", []) if m["id"] == modelo), None)
    if not target:
        return {"Aviso": f"Modelo '{modelo}' não encontrado no OpenRouter."}
    
    pricing = target.get("pricing", {})
    top_provider = target.get("top_provider", {})
    
    return {
        "Nome de Exibição": target.get("name"),
        "Janela de Contexto": target.get("context_length"),
        "Saída Máxima": top_provider.get("max_completion_tokens"),
        "Arquitetura/Modalidade": target.get("architecture", {}).get("modality"),
        "Tokenizer": target.get("architecture", {}).get("tokenizer"),
        "Preço Entrada (1M tokens)": f"${float(pricing.get('prompt', 0)) * 1_000_000:.4f}",
        "Preço Saída (1M tokens)": f"${float(pricing.get('completion', 0)) * 1_000_000:.4f}",
    }

# ==========================================
# 4. DISPATCHER E LOOP PRINCIPAL
# ==========================================

FUNCOES = {
    "gemini": consultar_gemini,
    "openai": consultar_openai,
    "maritaca": consultar_maritaca,
    "openrouter": consultar_openrouter,
}

def imprimir_resultado(provedor, dados_api, specs_estaticas):
    """Formata e imprime o resultado de cada modelo."""
    print("\n" + "=" * 70)
    print(f"🤖 MODELO: {MODELOS[provedor]['nome'].upper()} ({provedor.upper()})")
    print("=" * 70)
    
    print("📡 DADOS DINÂMICOS DA API:")
    if isinstance(dados_api, dict):
        for k, v in dados_api.items():
            print(f"  • {k}: {v}")
    else:
        print(f"  {dados_api}")
    
    if specs_estaticas:
        print("\n⚙️  ESPECIFICAÇÕES TÉCNICAS (Documentação Oficial):")
        for k, v in specs_estaticas.items():
            if isinstance(v, int):
                print(f"  • {k}: {v:,}")
            else:
                print(f"  • {k}: {v}")

def main():
    print("🔍 Coletando detalhes técnicos dos LLMs...")
    
    for provedor, config in MODELOS.items():
        try:
            dados_api = FUNCOES[provedor](
                modelo=config["nome"],
                base_url=config["url_base"],
                key=CHAVES[provedor],
            )
            specs = SPECS_CONHECIDAS.get(provedor)
            imprimir_resultado(provedor, dados_api, specs)
            
        except requests.exceptions.HTTPError as e:
            print(f"\n❌ [{provedor.upper()}] Erro HTTP: {e}")
        except requests.exceptions.ConnectionError:
            print(f"\n❌ [{provedor.upper()}] Falha de conexão. Verifique sua rede.")
        except Exception as e:
            print(f"\n❌ [{provedor.upper()}] Erro inesperado: {e}")
    
    print("\n" + "=" * 70)
    print("✅ Coleta finalizada.")

if __name__ == "__main__":
    main()