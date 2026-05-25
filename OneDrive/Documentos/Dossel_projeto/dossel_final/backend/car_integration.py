# ============================================================
# DOSSEL — Integração com CAR via Infosimples
# Arquivo: car_integration.py
# ============================================================
# Instalar dependências:
# pip install fastapi uvicorn requests python-dotenv
#
# Criar arquivo .env com:
# INFOSIMPLES_TOKEN=seu_token_aqui
#
# Rodar o servidor:
# uvicorn car_integration:app --reload --port 8000
# ============================================================
 
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Dossel CAR API")

# Permitir requisições do site Dossel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção: coloque só o domínio do site
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mapeamento de biomas da Dossel ───────────────────────────
BIOMAS = {
    "Amazônia":       { "co2": 180, "cresc": 4.5, "nome": "Amazônia" },
    "Cerrado":        { "co2": 80,  "cresc": 2.8, "nome": "Cerrado" },
    "Mata Atlântica": { "co2": 130, "cresc": 3.8, "nome": "Mata Atlântica" },
    "Caatinga":       { "co2": 40,  "cresc": 1.8, "nome": "Caatinga" },
    "Pantanal":       { "co2": 100, "cresc": 2.5, "nome": "Pantanal" },
    "Pampa":          { "co2": 35,  "cresc": 1.5, "nome": "Pampa" },
}

PRECO_TCO2 = 50  # R$/tCO2 — preço médio mercado voluntário Verra


# ── Endpoint principal: consulta o CAR e calcula potencial ───
@app.get("/consultar-car/{numero_car}")
def consultar_car(numero_car: str):
    """
    Recebe o número do CAR e retorna os dados da propriedade
    + cálculo do potencial de carbono da Dossel.
    
    Exemplo: GET /consultar-car/CE-2304400-XXXXXXXXXXXXXXXXXX
    """

    token = os.getenv("INFOSIMPLES_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="Token Infosimples não configurado.")

    # ── 1. Chama a API Infosimples ────────────────────────────
    try:
        response = requests.post(
            "https://api.infosimples.com/api/v2/consultas/car/demonstrativo",
            data={
                "car": numero_car,
                "token": token,
                "timeout": 300,
            },
            timeout=120,
        )
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar API: {str(e)}")

    # ── 2. Verifica se a consulta foi bem sucedida ────────────
    if data.get("code") != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Propriedade não encontrada. Verifique o número do CAR. Código: {data.get('code')}"
        )

    # ── 3. Extrai os dados da propriedade ─────────────────────
    dados = data.get("data", [{}])[0] if data.get("data") else {}

    area_total      = float(dados.get("area_total_ha", 0) or 0)
    area_vegetacao  = float(dados.get("area_vegetacao_nativa_ha", 0) or 0)
    area_app        = float(dados.get("area_app_ha", 0) or 0)
    area_reserva    = float(dados.get("area_reserva_legal_ha", 0) or 0)
    bioma           = dados.get("bioma", "Caatinga")
    municipio       = dados.get("municipio", "")
    estado          = dados.get("estado", "")
    situacao        = dados.get("situacao", "")
    nome_imovel     = dados.get("nome_imovel", "")

    # ── 4. Normaliza o bioma para os dados da Dossel ──────────
    bioma_dossel = "Caatinga"  # padrão
    for b in BIOMAS:
        if b.lower() in bioma.lower():
            bioma_dossel = b
            break

    dados_bioma = BIOMAS[bioma_dossel]

    # ── 5. Calcula potencial de carbono ───────────────────────
    # Usa vegetação nativa real do CAR
    # Se não tiver, estima como APP + Reserva Legal
    if area_vegetacao > 0:
        area_elegivel = area_vegetacao
    elif area_app + area_reserva > 0:
        area_elegivel = area_app + area_reserva
    else:
        area_elegivel = area_total * 0.20  # estimativa mínima: 20%

    pct_vegetacao   = (area_elegivel / area_total * 100) if area_total > 0 else 0
    co2_anual       = area_elegivel * dados_bioma["co2"] * dados_bioma["cresc"] / 100
    receita_bruta   = co2_anual * PRECO_TCO2
    receita_produtor = receita_bruta * 0.85
    receita_dossel  = receita_bruta * 0.15
    receita_10_anos = receita_produtor * 10

    # ── 6. Define classificação de potencial ──────────────────
    if co2_anual >= 500:
        potencial = "Alto"
    elif co2_anual >= 50:
        potencial = "Médio"
    else:
        potencial = "Baixo"

    # ── 7. Retorna resposta completa ──────────────────────────
    return {
        "status": "ok",
        "propriedade": {
            "numero_car":    numero_car,
            "nome":          nome_imovel,
            "municipio":     municipio,
            "estado":        estado,
            "bioma":         bioma,
            "situacao_car":  situacao,
            "area_total_ha": area_total,
            "area_app_ha":   area_app,
            "area_reserva_ha": area_reserva,
            "area_vegetacao_ha": area_vegetacao,
        },
        "calculo_dossel": {
            "bioma_usado":         bioma_dossel,
            "area_elegivel_ha":    round(area_elegivel, 2),
            "pct_vegetacao":       round(pct_vegetacao, 1),
            "co2_anual_tco2":      round(co2_anual, 2),
            "preco_tco2_brl":      PRECO_TCO2,
            "receita_bruta_ano":   round(receita_bruta, 2),
            "receita_produtor_ano": round(receita_produtor, 2),
            "receita_dossel_ano":  round(receita_dossel, 2),
            "receita_produtor_10anos": round(receita_10_anos, 2),
            "potencial":           potencial,
        },
        "mensagem": f"Propriedade com {potencial.lower()} potencial de carbono. "
                    f"{round(area_elegivel, 1)} ha elegíveis em {bioma_dossel} = "
                    f"R$ {round(receita_produtor, 0):,.0f}/ano para o produtor."
    }


# ── Endpoint de teste sem gastar créditos ────────────────────
@app.get("/teste")
def teste():
    """Retorna dados simulados para testar a integração sem gastar créditos."""
    return {
        "status": "ok",
        "propriedade": {
            "numero_car":    "CE-2304400-TESTE000000000",
            "nome":          "Fazenda Boa Esperança",
            "municipio":     "Juazeiro do Norte",
            "estado":        "Ceará",
            "bioma":         "Caatinga",
            "situacao_car":  "Ativo",
            "area_total_ha": 200,
            "area_app_ha":   20,
            "area_reserva_ha": 40,
            "area_vegetacao_ha": 80,
        },
        "calculo_dossel": {
            "bioma_usado":         "Caatinga",
            "area_elegivel_ha":    80,
            "pct_vegetacao":       40.0,
            "co2_anual_tco2":      57.6,
            "preco_tco2_brl":      50,
            "receita_bruta_ano":   2880,
            "receita_produtor_ano": 2448,
            "receita_dossel_ano":  432,
            "receita_produtor_10anos": 24480,
            "potencial":           "Médio",
        },
        "mensagem": "Propriedade com médio potencial de carbono. 80 ha elegíveis em Caatinga = R$ 2.448/ano para o produtor."
    }


# ── Rodar localmente ──────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)