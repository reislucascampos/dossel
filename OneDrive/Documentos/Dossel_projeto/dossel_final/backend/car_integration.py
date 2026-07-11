# ============================================================
# DOSSEL — Integração com CAR via SICAR/SFB (gratuito)
# Arquivo: car_integration.py
#
# Fonte: geoserver.car.gov.br — dados abertos do governo federal
# Sem token, sem custo, sem dependência externa.
#
# Instalar dependências:
# pip install fastapi uvicorn requests
#
# Rodar o servidor:
# uvicorn car_integration:app --reload --port 8000
# ============================================================

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Dossel CAR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Parâmetros de cálculo por bioma ─────────────────────────
BIOMAS = {
    "Amazônia":       {"co2": 180, "cresc": 4.5},
    "Cerrado":        {"co2": 80,  "cresc": 2.8},
    "Mata Atlântica": {"co2": 130, "cresc": 3.8},
    "Caatinga":       {"co2": 40,  "cresc": 1.8},
    "Pantanal":       {"co2": 100, "cresc": 2.5},
    "Pampa":          {"co2": 35,  "cresc": 1.5},
}

PRECO_TCO2 = 82  # R$/tCO₂e — cotação média Safra 2026

# ── Bioma predominante por UF ────────────────────────────────
# Simplificação necessária: SICAR não retorna bioma diretamente.
BIOMA_POR_UF = {
    "AC": "Amazônia", "AM": "Amazônia", "PA": "Amazônia",
    "RO": "Amazônia", "RR": "Amazônia", "AP": "Amazônia",
    "CE": "Caatinga", "RN": "Caatinga", "PB": "Caatinga",
    "PE": "Caatinga", "AL": "Caatinga", "SE": "Caatinga",
    "PI": "Caatinga", "BA": "Caatinga",
    "SP": "Mata Atlântica", "RJ": "Mata Atlântica",
    "ES": "Mata Atlântica", "PR": "Mata Atlântica",
    "SC": "Mata Atlântica",
    "GO": "Cerrado", "DF": "Cerrado", "TO": "Cerrado",
    "MT": "Cerrado", "MG": "Cerrado", "MA": "Cerrado",
    "MS": "Pantanal",
    "RS": "Pampa",
}

SICAR_WFS = "https://geoserver.car.gov.br/geoserver/sicar/wfs"


def _uf_do_car(numero_car: str) -> str:
    return numero_car[:2].upper()


def _layer_do_uf(uf: str) -> str:
    return f"sicar:sicar_imoveis_{uf.lower()}"


# ── Endpoint principal ───────────────────────────────────────
@app.get("/consultar-car/{numero_car}")
def consultar_car(numero_car: str):
    """
    Consulta o SICAR (gratuito) e retorna dados da propriedade
    + cálculo do potencial de carbono Dossel.

    Exemplo: GET /consultar-car/CE-2304400-XXXXXXXXXXXXXXXXXX
    """
    uf    = _uf_do_car(numero_car)
    layer = _layer_do_uf(uf)

    # ── 1. Consulta o SICAR WFS ───────────────────────────────
    try:
        resp = requests.get(
            SICAR_WFS,
            params={
                "service":      "WFS",
                "version":      "2.0.0",
                "request":      "GetFeature",
                "typeNames":    layer,
                "outputFormat": "application/json",
                "CQL_FILTER":   f"cod_imovel='{numero_car}'",
                "count":        1,
            },
            timeout=30,
        )
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar SICAR: {str(e)}")

    features = data.get("features", [])
    if not features:
        raise HTTPException(
            status_code=404,
            detail="Propriedade não encontrada no SICAR. Verifique o número do CAR."
        )

    # ── 2. Extrai campos disponíveis ──────────────────────────
    props      = features[0].get("properties", {})
    area_total = float(props.get("area", 0) or 0)
    municipio  = props.get("municipio", "")
    estado     = props.get("uf", uf)
    situacao   = props.get("status_imovel", "")
    condicao   = props.get("condicao", "")

    # ── 3. Determina bioma pelo estado ────────────────────────
    bioma_dossel = BIOMA_POR_UF.get(estado, "Caatinga")
    dados_bioma  = BIOMAS[bioma_dossel]

    # ── 4. Estima área elegível (30% conservador) ─────────────
    # SICAR não fornece breakdown de vegetação/APP/RL na API WFS.
    # Usamos 30% da área total como estimativa mínima conservadora.
    area_elegivel = area_total * 0.30
    pct_vegetacao = 30.0

    # ── 5. Calcula potencial de carbono ───────────────────────
    co2_anual        = area_elegivel * dados_bioma["co2"] * dados_bioma["cresc"] / 100
    receita_bruta    = co2_anual * PRECO_TCO2
    receita_produtor = receita_bruta * 0.85
    receita_dossel   = receita_bruta * 0.15
    receita_10_anos  = receita_produtor * 10

    if co2_anual >= 500:
        potencial = "Alto"
    elif co2_anual >= 50:
        potencial = "Médio"
    else:
        potencial = "Baixo"

    # ── 6. Retorna resposta ───────────────────────────────────
    return {
        "status": "ok",
        "propriedade": {
            "numero_car":       numero_car,
            "municipio":        municipio,
            "estado":           estado,
            "bioma":            bioma_dossel,
            "situacao_car":     situacao,
            "condicao":         condicao,
            "area_total_ha":    area_total,
            "area_app_ha":      None,
            "area_reserva_ha":  None,
            "area_vegetacao_ha": None,
        },
        "calculo_dossel": {
            "bioma_usado":             bioma_dossel,
            "area_elegivel_ha":        round(area_elegivel, 2),
            "pct_vegetacao":           pct_vegetacao,
            "co2_anual_tco2":          round(co2_anual, 2),
            "preco_tco2_brl":          PRECO_TCO2,
            "receita_bruta_ano":       round(receita_bruta, 2),
            "receita_produtor_ano":    round(receita_produtor, 2),
            "receita_dossel_ano":      round(receita_dossel, 2),
            "receita_produtor_10anos": round(receita_10_anos, 2),
            "potencial":               potencial,
        },
        "mensagem": (
            f"Propriedade com {potencial.lower()} potencial de carbono. "
            f"{round(area_elegivel, 1)} ha elegíveis estimados em {bioma_dossel} = "
            f"R$ {round(receita_produtor, 0):,.0f}/ano para o produtor."
        ),
        "fonte": "SICAR/SFB — dados abertos do governo federal",
        "nota": "Área elegível estimada em 30% da área total (conservador). "
                "Análise detalhada disponível após cadastro.",
    }


# ── Endpoint de teste sem chamada externa ────────────────────
@app.get("/teste")
def teste():
    return {
        "status": "ok",
        "propriedade": {
            "numero_car":       "CE-2304400-TESTE000000000",
            "municipio":        "Juazeiro do Norte",
            "estado":           "CE",
            "bioma":            "Caatinga",
            "situacao_car":     "AT",
            "condicao":         "Ativo",
            "area_total_ha":    200,
            "area_app_ha":      None,
            "area_reserva_ha":  None,
            "area_vegetacao_ha": None,
        },
        "calculo_dossel": {
            "bioma_usado":             "Caatinga",
            "area_elegivel_ha":        60,
            "pct_vegetacao":           30.0,
            "co2_anual_tco2":          43.2,
            "preco_tco2_brl":          82,
            "receita_bruta_ano":       3542,
            "receita_produtor_ano":    3011,
            "receita_dossel_ano":      531,
            "receita_produtor_10anos": 30110,
            "potencial":               "Médio",
        },
        "mensagem": "Propriedade com médio potencial de carbono. 60 ha elegíveis em Caatinga = R$ 3.011/ano para o produtor.",
        "fonte": "SICAR/SFB — dados abertos do governo federal",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
