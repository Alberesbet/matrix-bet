import os, time, threading, statistics
from datetime import datetime, timedelta
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
    "intervalo": int(os.getenv("MATRIX_INTERVALO", "180")),
    "dias_busca": int(os.getenv("MATRIX_DIAS_BUSCA", "7")),
    "modo": os.getenv("MATRIX_MODO", "SIMULACAO"),
}

STATE = {
    "status": "iniciando",
    "ultima_atualizacao": None,
    "jogos_encontrados": 0,
    "jogos_com_odds": 0,
    "jogos_analisados": 0,
    "libertadores": [],
    "internacionais": [],
    "ao_vivo": [],
    "sinais": [],
    "todos": [],
    "erro": None,
}

LOCK = threading.Lock()
app = FastAPI(title="MATRIX - FUTEBOL")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def agora():
    return datetime.now(TZ)


def get_token():
    t = os.getenv("SPORTMONKS_TOKEN", "").strip()
    if not t:
        raise RuntimeError("SPORTMONKS_TOKEN não configurado no Render.")
    return t


def api_get(path, params=None):
    p = dict(params or {})
    p["api_token"] = get_token()
    r = requests.get(BASE + path, params=p, timeout=30, headers={"Accept": "application/json"})
    try:
        payload = r.json()
    except Exception:
        payload = {}
    if r.status_code >= 400:
        msg = payload.get("message") if isinstance(payload, dict) else None
        raise RuntimeError(msg or f"SportMonks HTTP {r.status_code}")
    return payload


def get_all_pages(path, params=None, max_pages=12):
    out = []
    page = 1
    while page <= max_pages:
        p = dict(params or {})
        p["page"] = page
        payload = api_get(path, p)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if isinstance(data, list):
            out.extend(data)
        pagination = payload.get("pagination") or {}
        if not data:
            break
        if pagination.get("has_more") is False:
            break
        if not pagination:
            break
        page += 1
    return out


def team_names(f):
    home = away = None
    for p in f.get("participants") or []:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if loc == "home":
            home = p.get("name")
        elif loc == "away":
            away = p.get("name")
    if not home or not away:
        name = str(f.get("name") or "")
        for sep in (" vs ", " v ", " - "):
            if sep in name:
                a, b = name.split(sep, 1)
                home = home or a.strip()
                away = away or b.strip()
                break
    return home or "Casa", away or "Fora"


def league_name(f):
    return str((f.get("league") or {}).get("name") or f.get("league_id") or "Liga")


def is_libertadores(f):
    name = league_name(f).lower()
    return "libertadores" in name


def is_international(f):
    name = league_name(f).lower()
    keys = (
        "libertadores", "sudamericana", "champions", "europa league",
        "conference league", "uefa", "conmebol", "world cup",
        "club world cup", "nations league", "international"
    )
    return any(k in name for k in keys)


def local_start(f):
    raw = f.get("starting_at")
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ).strftime("%d/%m %H:%M")
    except Exception:
        return str(raw)


def score_live(f):
    participants = f.get("participants") or []
    ids = {}
    for p in participants:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if loc in ("home", "away"):
            ids[p.get("id")] = loc

    home = away = None
    for s in f.get("scores") or []:
        desc = str(s.get("description") or "").upper()
        if desc not in ("CURRENT", "2ND_HALF", "1ST_HALF", "EXTRA_TIME", "PENALTY_SHOOTOUT"):
            continue
        pid = s.get("participant_id")
        goals = (s.get("score") or {}).get("goals")
        if ids.get(pid) == "home":
            home = goals
        elif ids.get(pid) == "away":
            away = goals

    if home is None or away is None:
        # Fallback: pega os últimos valores conhecidos por participante.
        last = {}
        for s in f.get("scores") or []:
            pid = s.get("participant_id")
            goals = (s.get("score") or {}).get("goals")
            if pid is not None and goals is not None:
                last[pid] = goals
        for pid, loc in ids.items():
            if loc == "home" and pid in last:
                home = last[pid]
            if loc == "away" and pid in last:
                away = last[pid]

    if home is None or away is None:
        return "-"
    return f"{home} x {away}"


def state_text(f):
    st = f.get("state") or {}
    return str(st.get("short_name") or st.get("name") or f.get("state_id") or "AO VIVO")


def upcoming_fixtures():
    start = agora().date()
    end = (agora() + timedelta(days=CONFIG["dias_busca"])).date()
    rows = get_all_pages(
        f"/fixtures/between/{start.isoformat()}/{end.isoformat()}",
        {"include": "participants;league;state"}
    )
    seen, out = set(), []
    for f in rows:
        fid = f.get("id")
        if fid in seen:
            continue
        seen.add(fid)
        out.append(f)
    return out


def live_fixtures():
    # Endpoint oficial de partidas em andamento.
    payload = api_get(
        "/livescores/inplay",
        {"include": "participants;league;state;scores"}
    )
    return payload.get("data", []) if isinstance(payload, dict) else []


def prematch_odds(fid):
    return get_all_pages(
        f"/odds/pre-match/fixtures/{fid}",
        {"include": "market;bookmaker"},
        max_pages=8
    )


def live_odds(fid):
    # Pode não estar liberado no plano contratado.
    try:
        return get_all_pages(
            f"/odds/inplay/fixtures/{fid}",
            {"include": "market;bookmaker"},
            max_pages=6
        ), None
    except Exception as e:
        return [], str(e)


def norm_label(raw):
    x = str(raw or "").strip().upper()
    return {
        "1": "HOME", "HOME": "HOME", "CASA": "HOME",
        "X": "DRAW", "DRAW": "DRAW", "EMPATE": "DRAW",
        "2": "AWAY", "AWAY": "AWAY", "FORA": "AWAY",
    }.get(x)


def parse_1x2(rows):
    buckets = {"HOME": [], "DRAW": [], "AWAY": []}
    for o in rows:
        desc = str(
            o.get("market_description")
            or (o.get("market") or {}).get("name")
            or (o.get("market") or {}).get("developer_name")
            or ""
        ).upper()
        ok = (
            "FULLTIME RESULT" in desc
            or "FULL TIME RESULT" in desc
            or "MATCH WINNER" in desc
            or "1X2" in desc
            or o.get("market_id") in (1, 52, 856)
        )
        if not ok:
            continue
        key = norm_label(o.get("label") or o.get("name") or o.get("selection"))
        if not key:
            continue
        try:
            val = float(o.get("value"))
        except Exception:
            continue
        if val > 1.0:
            buckets[key].append(val)

    out = {}
    for key, vals in buckets.items():
        if vals:
            med = statistics.median(vals)
            out[key] = {
                "odd": med,
                "best": max(vals),
                "n": len(vals),
            }

    total = sum(1 / v["odd"] for v in out.values()) or 1
    for v in out.values():
        v["prob"] = (1 / v["odd"]) / total
    return out


def analyze_market(f, rows, live=False, odds_error=None):
    home, away = team_names(f)
    name = f"{home} x {away}"
    league = league_name(f)
    m = parse_1x2(rows)

    base = {
        "fixture_id": f.get("id"),
        "jogo": name,
        "liga": league,
        "horario": local_start(f),
        "libertadores": is_libertadores(f),
        "internacional": is_international(f),
        "ao_vivo": live,
        "placar": score_live(f) if live else None,
        "estado": state_text(f) if live else None,
    }

    if not m:
        base.update({
            "status": "SEM 1X2" if not odds_error else "ODDS LIVE INDISPONÍVEIS",
            "motivo": odds_error or "Partida encontrada, mas sem mercado 1X2 disponível.",
        })
        return base, None

    sel, v = max(m.items(), key=lambda x: x[1]["prob"])
    pick = {"HOME": home, "DRAW": "Empate", "AWAY": away}[sel]
    reasons = []
    if not (CONFIG["odd_min"] <= v["odd"] <= CONFIG["odd_max"]):
        reasons.append(f"odd {v['odd']:.2f} fora do filtro")
    if v["prob"] < CONFIG["prob_min"]:
        reasons.append(f"probabilidade implícita {v['prob']*100:.1f}% abaixo do filtro")

    approved = not reasons
    item = {
        **base,
        "mercado": "Resultado da partida (1X2)",
        "selecao": pick,
        "odd": round(v["odd"], 2),
        "melhor_odd": round(v["best"], 2),
        "casas": v["n"],
        "prob": round(v["prob"] * 100, 1),
        "stake": CONFIG["stake"],
        "status": "APROVADO" if approved else "AGUARDAR",
        "motivo": "Passou pelos filtros." if approved else "; ".join(reasons),
    }
    return item, item if approved else None


def run_analysis():
    with LOCK:
        STATE["status"] = "analisando"
        STATE["erro"] = None

    try:
        upcoming = upcoming_fixtures()
        live = live_fixtures()

        todos, sinais = [], []
        with_odds = analyzed = 0

        for f in upcoming:
            if not f.get("has_odds"):
                home, away = team_names(f)
                item = {
                    "fixture_id": f.get("id"),
                    "jogo": f"{home} x {away}",
                    "liga": league_name(f),
                    "horario": local_start(f),
                    "libertadores": is_libertadores(f),
                    "internacional": is_international(f),
                    "ao_vivo": False,
                    "status": "SEM ODDS",
                    "motivo": "A SportMonks informou que esta partida não possui odds disponíveis.",
                }
                todos.append(item)
                continue

            with_odds += 1
            try:
                odds = prematch_odds(f.get("id"))
            except Exception as e:
                odds = []
                err = str(e)
            else:
                err = None

            item, signal = analyze_market(f, odds, live=False, odds_error=err)
            if item.get("odd") is not None:
                analyzed += 1
            todos.append(item)
            if signal:
                sinais.append(signal)

        live_items = []
        for f in live:
            odds, live_err = live_odds(f.get("id"))
            item, signal = analyze_market(f, odds, live=True, odds_error=live_err)
            live_items.append(item)
            # Sinal ao vivo só é marcado se a API realmente forneceu odds live.
            if signal:
                signal["tipo_sinal"] = "AO VIVO"
                sinais.append(signal)

        libertadores = [x for x in todos if x.get("libertadores")]
        internacionais = [x for x in todos if x.get("internacional")]

        with LOCK:
            STATE.update({
                "status": "online",
                "ultima_atualizacao": agora().isoformat(timespec="seconds"),
                "jogos_encontrados": len(upcoming),
                "jogos_com_odds": with_odds,
                "jogos_analisados": analyzed,
                "libertadores": libertadores,
                "internacionais": internacionais,
                "ao_vivo": live_items,
                "sinais": sinais,
                "todos": todos,
                "erro": None,
            })
    except Exception as e:
        with LOCK:
            STATE["status"] = "erro"
            STATE["erro"] = str(e)
            STATE["ultima_atualizacao"] = agora().isoformat(timespec="seconds")


def worker():
    while True:
        run_analysis()
        time.sleep(CONFIG["intervalo"])


@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/status")
def status():
    with LOCK:
        return JSONResponse({
            "nome": "MATRIX - FUTEBOL",
            "versao": "V3.2 LIBERTADORES + INTERNACIONAL + AO VIVO",
            "config": CONFIG,
            **STATE,
        })


@app.post("/api/analisar")
def analisar():
    run_analysis()
    return status()


@app.get("/health")
def health():
    return {"ok": True, "versao": "3.2"}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))
