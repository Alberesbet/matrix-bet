
import os, time, threading, statistics
from datetime import datetime
from typing import Dict, Any, List

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = "https://api.sportmonks.com/v3/football"

CONFIG = {
    "stake": float(os.getenv("MATRIX_STAKE", "10")),
    "odd_min": float(os.getenv("MATRIX_ODD_MIN", "1.45")),
    "odd_max": float(os.getenv("MATRIX_ODD_MAX", "3.50")),
    "prob_min": float(os.getenv("MATRIX_PROB_MIN", "0.55")),
    "intervalo": int(os.getenv("MATRIX_INTERVALO", "300")),
    "modo": os.getenv("MATRIX_MODO", "SIMULACAO"),
}

STATE: Dict[str, Any] = {
    "status": "iniciando",
    "ultima_atualizacao": None,
    "jogos_encontrados": 0,
    "sinais": [],
    "erro": None,
}

app = FastAPI(title="MATRIX - FUTEBOL")
app.mount("/static", StaticFiles(directory="static"), name="static")

def token() -> str:
    t = os.getenv("SPORTMONKS_TOKEN", "").strip()
    if not t:
        raise RuntimeError("SPORTMONKS_TOKEN não configurado no Render.")
    return t

def api_get(path: str, params=None):
    p = dict(params or {})
    p["api_token"] = token()
    r = requests.get(BASE + path, params=p, timeout=30, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()

def jogos_hoje():
    d = datetime.now().strftime("%Y-%m-%d")
    return api_get(f"/fixtures/between/{d}/{d}", {"include": "participants;league;state"}).get("data", [])

def odds_fixture(fid):
    return api_get(f"/odds/pre-match/fixtures/{fid}", {"include": "market;bookmaker"}).get("data", [])

def times(f):
    home = away = None
    for p in f.get("participants") or []:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if loc == "home":
            home = p.get("name")
        elif loc == "away":
            away = p.get("name")
    return home or "Casa", away or "Fora"

def mercado_1x2(rows):
    grupos = {"HOME": [], "DRAW": [], "AWAY": []}
    alias = {
        "1": "HOME", "HOME": "HOME", "CASA": "HOME",
        "X": "DRAW", "DRAW": "DRAW", "EMPATE": "DRAW",
        "2": "AWAY", "AWAY": "AWAY", "FORA": "AWAY",
    }
    for o in rows:
        desc = str(o.get("market_description") or (o.get("market") or {}).get("name") or "").upper()
        if o.get("market_id") != 1 and "MATCH WINNER" not in desc and "1X2" not in desc:
            continue
        key = alias.get(str(o.get("label") or o.get("name") or "").strip().upper())
        try:
            odd = float(o.get("value"))
        except Exception:
            continue
        if key and odd > 1:
            grupos[key].append(odd)

    out = {}
    for key, vals in grupos.items():
        if vals:
            out[key] = {"odd": statistics.median(vals)}

    total = sum(1 / v["odd"] for v in out.values()) or 1
    for v in out.values():
        v["prob"] = (1 / v["odd"]) / total
    return out

def analisar_uma_vez():
    STATE["status"] = "analisando"
    STATE["erro"] = None
    sinais = []
    try:
        jogos = jogos_hoje()
        STATE["jogos_encontrados"] = len(jogos)

        for f in jogos:
            if not f.get("has_odds"):
                continue

            fid = f.get("id")
            home, away = times(f)

            try:
                mercado = mercado_1x2(odds_fixture(fid))
            except Exception:
                continue

            candidatos = [
                (sel, v)
                for sel, v in mercado.items()
                if CONFIG["odd_min"] <= v["odd"] <= CONFIG["odd_max"]
                and v["prob"] >= CONFIG["prob_min"]
            ]

            if candidatos:
                sel, v = max(candidatos, key=lambda x: x[1]["prob"])
                sinais.append({
                    "fixture_id": fid,
                    "jogo": f"{home} x {away}",
                    "selecao": sel,
                    "odd": round(v["odd"], 2),
                    "prob": round(v["prob"] * 100, 1),
                    "stake": CONFIG["stake"],
                    "modo": CONFIG["modo"],
                })

        STATE["sinais"] = sinais
        STATE["ultima_atualizacao"] = datetime.now().isoformat(timespec="seconds")
        STATE["status"] = "online"
    except Exception as e:
        STATE["erro"] = str(e)
        STATE["status"] = "erro"
        STATE["ultima_atualizacao"] = datetime.now().isoformat(timespec="seconds")

def worker():
    while True:
        analisar_uma_vez()
        time.sleep(CONFIG["intervalo"])

@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()

@app.get("/api/status")
def status():
    return JSONResponse({
        "nome": "MATRIX - FUTEBOL",
        "versao": "V2 RENDER MOBILE",
        "config": CONFIG,
        **STATE
    })

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))
