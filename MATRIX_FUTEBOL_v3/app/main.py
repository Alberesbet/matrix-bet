import os, time, threading, statistics
from datetime import datetime, timedelta
from typing import Dict, Any
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = "https://api.sportmonks.com/v3/football"
TZ = ZoneInfo(os.getenv("MATRIX_TIMEZONE", "America/Sao_Paulo"))
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

CONFIG = {
    "stake": float(os.getenv("MATRIX_STAKE", "10")),
    "odd_min": float(os.getenv("MATRIX_ODD_MIN", "1.35")),
    "odd_max": float(os.getenv("MATRIX_ODD_MAX", "4.00")),
    "prob_min": float(os.getenv("MATRIX_PROB_MIN", "0.45")),
    "intervalo": int(os.getenv("MATRIX_INTERVALO", "300")),
    "modo": os.getenv("MATRIX_MODO", "SIMULACAO"),
}

STATE: Dict[str, Any] = {
    "status": "iniciando",
    "ultima_atualizacao": None,
    "jogos_encontrados": 0,
    "jogos_com_odds": 0,
    "jogos_analisados": 0,
    "sinais": [],
    "diagnostico": [],
    "erro": None,
}

LOCK = threading.Lock()
app = FastAPI(title="MATRIX - FUTEBOL")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def agora():
    return datetime.now(TZ)


def token() -> str:
    t = os.getenv("SPORTMONKS_TOKEN", "").strip()
    if not t:
        raise RuntimeError("SPORTMONKS_TOKEN não configurado no Render.")
    return t


def api_get(path: str, params=None):
    p = dict(params or {})
    p["api_token"] = token()
    r = requests.get(
        BASE + path,
        params=p,
        timeout=30,
        headers={"Accept": "application/json"}
    )
    try:
        payload = r.json()
    except Exception:
        payload = {}
    if r.status_code >= 400:
        msg = payload.get("message") if isinstance(payload, dict) else None
        raise RuntimeError(msg or f"SportMonks HTTP {r.status_code}")
    return payload


def jogos_24h():
    # Busca hoje e amanhã no horário do Brasil para não perder jogos na virada do dia.
    inicio = agora().date()
    fim = (agora() + timedelta(days=1)).date()
    data = api_get(
        f"/fixtures/between/{inicio.isoformat()}/{fim.isoformat()}",
        {"include": "participants;league;state"}
    ).get("data", [])

    # Mantém somente os próximos ~24h quando houver horário parseável.
    limite = agora() + timedelta(hours=24)
    saida = []
    for f in data:
        raw = f.get("starting_at")
        if not raw:
            saida.append(f)
            continue
        try:
            # SportMonks costuma retornar "YYYY-MM-DD HH:MM:SS"
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            local = dt.astimezone(TZ)
            if agora() - timedelta(hours=3) <= local <= limite:
                f["_local_start"] = local.isoformat(timespec="minutes")
                saida.append(f)
        except Exception:
            saida.append(f)
    return saida


def odds_fixture(fid):
    return api_get(
        f"/odds/pre-match/fixtures/{fid}",
        {"include": "market;bookmaker"}
    ).get("data", [])


def times(f):
    home = away = None
    for p in f.get("participants") or []:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if loc == "home":
            home = p.get("name")
        elif loc == "away":
            away = p.get("name")

    if not home or not away:
        name = str(f.get("name") or "")
        parts = re_split_match(name)
        if not home and parts:
            home = parts[0]
        if not away and len(parts) > 1:
            away = parts[1]

    return home or "Casa", away or "Fora"


def re_split_match(name):
    # Sem depender de regex global no restante do app.
    for sep in (" vs ", " v ", " - "):
        if sep in name:
            return [x.strip() for x in name.split(sep, 1)]
    return [name.strip()] if name.strip() else []


def normalize_label(raw):
    x = str(raw or "").strip().upper()
    aliases = {
        "1": "HOME", "HOME": "HOME", "CASA": "HOME", "LOCAL": "HOME",
        "X": "DRAW", "DRAW": "DRAW", "EMPATE": "DRAW",
        "2": "AWAY", "AWAY": "AWAY", "FORA": "AWAY", "VISITANTE": "AWAY",
    }
    return aliases.get(x)


def mercado_1x2(rows):
    grupos = {"HOME": [], "DRAW": [], "AWAY": []}
    detalhes = {"HOME": [], "DRAW": [], "AWAY": []}

    for o in rows:
        market = o.get("market") or {}
        desc = str(
            o.get("market_description")
            or market.get("name")
            or market.get("developer_name")
            or ""
        ).upper()

        # SportMonks pode variar market_id por feed/provedor.
        market_ok = (
            "MATCH WINNER" in desc
            or "1X2" in desc
            or "FULLTIME RESULT" in desc
            or "FULL TIME RESULT" in desc
            or "3 WAY" in desc
            or "3-WAY" in desc
            or o.get("market_id") in (1, 52, 856)
        )
        if not market_ok:
            continue

        key = normalize_label(
            o.get("label")
            or o.get("name")
            or o.get("selection")
            or o.get("value_label")
        )
        if not key:
            continue

        try:
            odd = float(o.get("value"))
        except Exception:
            continue

        if odd <= 1.0:
            continue

        grupos[key].append(odd)
        detalhes[key].append({
            "odd": odd,
            "bookmaker": (o.get("bookmaker") or {}).get("name") or "",
        })

    out = {}
    for key, vals in grupos.items():
        if vals:
            med = statistics.median(vals)
            out[key] = {
                "odd": med,
                "amostras": len(vals),
                "melhor_odd": max(vals),
            }

    # Probabilidade implícita sem vigorish, normalizada entre as seleções disponíveis.
    soma = sum(1 / v["odd"] for v in out.values()) or 1
    for v in out.values():
        v["prob"] = (1 / v["odd"]) / soma

    return out


def hora_jogo(f):
    if f.get("_local_start"):
        try:
            return datetime.fromisoformat(f["_local_start"]).strftime("%d/%m %H:%M")
        except Exception:
            pass
    raw = f.get("starting_at")
    return str(raw or "-")


def analisar_uma_vez():
    with LOCK:
        STATE["status"] = "analisando"
        STATE["erro"] = None

    sinais = []
    diagnostico = []

    try:
        jogos = jogos_24h()
        jogos_com_odds = 0
        jogos_analisados = 0

        for f in jogos:
            fid = f.get("id")
            home, away = times(f)
            jogo_nome = f"{home} x {away}"
            liga = (f.get("league") or {}).get("name") or f.get("league_id") or "Liga"
            horario = hora_jogo(f)

            if not f.get("has_odds"):
                diagnostico.append({
                    "fixture_id": fid,
                    "jogo": jogo_nome,
                    "liga": liga,
                    "horario": horario,
                    "status": "SEM ODDS",
                    "motivo": "A SportMonks informou has_odds=false para esta partida.",
                })
                continue

            jogos_com_odds += 1

            try:
                rows = odds_fixture(fid)
                mercado = mercado_1x2(rows)
            except Exception as e:
                diagnostico.append({
                    "fixture_id": fid,
                    "jogo": jogo_nome,
                    "liga": liga,
                    "horario": horario,
                    "status": "ERRO NAS ODDS",
                    "motivo": str(e),
                })
                continue

            if not mercado:
                diagnostico.append({
                    "fixture_id": fid,
                    "jogo": jogo_nome,
                    "liga": liga,
                    "horario": horario,
                    "status": "SEM 1X2",
                    "motivo": f"Recebidas {len(rows)} cotações, mas não encontrei Casa/Empate/Fora no feed.",
                })
                continue

            jogos_analisados += 1
            sel, v = max(mercado.items(), key=lambda x: x[1]["prob"])
            selecao_nome = {"HOME": home, "DRAW": "Empate", "AWAY": away}.get(sel, sel)

            filtros = []
            if not (CONFIG["odd_min"] <= v["odd"] <= CONFIG["odd_max"]):
                filtros.append(f"odd {v['odd']:.2f} fora de {CONFIG['odd_min']:.2f}–{CONFIG['odd_max']:.2f}")
            if v["prob"] < CONFIG["prob_min"]:
                filtros.append(f"probabilidade {v['prob']*100:.1f}% abaixo de {CONFIG['prob_min']*100:.0f}%")

            aprovado = not filtros
            item = {
                "fixture_id": fid,
                "jogo": jogo_nome,
                "liga": liga,
                "horario": horario,
                "mercado": "Resultado da partida (1X2)",
                "selecao": selecao_nome,
                "codigo_selecao": sel,
                "odd": round(v["odd"], 2),
                "melhor_odd": round(v["melhor_odd"], 2),
                "casas": v["amostras"],
                "prob": round(v["prob"] * 100, 1),
                "prob_tipo": "probabilidade implícita normalizada pelas odds",
                "status_sinal": "APROVADO" if aprovado else "AGUARDAR",
                "motivo": "Passou pelos filtros." if aprovado else "; ".join(filtros),
                "stake": CONFIG["stake"],
                "modo": CONFIG["modo"],
            }

            diagnostico.append(item)
            if aprovado:
                sinais.append(item)

        with LOCK:
            STATE["jogos_encontrados"] = len(jogos)
            STATE["jogos_com_odds"] = jogos_com_odds
            STATE["jogos_analisados"] = jogos_analisados
            STATE["sinais"] = sinais
            STATE["diagnostico"] = diagnostico
            STATE["ultima_atualizacao"] = agora().isoformat(timespec="seconds")
            STATE["status"] = "online"

    except Exception as e:
        with LOCK:
            STATE["erro"] = str(e)
            STATE["status"] = "erro"
            STATE["ultima_atualizacao"] = agora().isoformat(timespec="seconds")


def worker():
    while True:
        analisar_uma_vez()
        time.sleep(CONFIG["intervalo"])


@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/status")
def status():
    with LOCK:
        payload = {
            "nome": "MATRIX - FUTEBOL",
            "versao": "V3.1 DIAGNOSTICO MOBILE",
            "config": CONFIG,
            **STATE,
        }
    return JSONResponse(payload)


@app.post("/api/analisar")
def analisar_agora():
    analisar_uma_vez()
    return status()


@app.get("/health")
def health():
    return {"ok": True, "versao": "3.1"}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))
