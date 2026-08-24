import os, time, threading, statistics, csv, io
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
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
    "dias_busca": int(os.getenv("MATRIX_DIAS_BUSCA", "30")),
    "h2h_jogos": int(os.getenv("MATRIX_H2H_JOGOS", "5")),
    "modo": "SIMULACAO",
    "bfbot_provider": os.getenv("BFBOT_PROVIDER", "MATRIX"),
    "bfbot_enabled": os.getenv("BFBOT_ENABLED", "true").strip().lower() in ("1","true","yes","sim"),
    "bfbot_min_minutes_before_start": int(os.getenv("BFBOT_MIN_MINUTES_BEFORE_START", "0")),
    "bfbot_max_tips": int(os.getenv("BFBOT_MAX_TIPS", "20")),
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

LOCK = threading.RLock()
H2H_CACHE = {}
H2H_TTL = 12 * 60 * 60


def _mask(value, keep_start=2, keep_end=2):
    value = str(value or "").strip()
    if not value:
        return "-"
    if len(value) <= keep_start + keep_end:
        return "*" * len(value)
    return value[:keep_start] + ("*" * (len(value) - keep_start - keep_end)) + value[-keep_end:]


def account_info():
    """
    Informações visíveis da conta.
    Credenciais reais (senha/token/API key) NÃO são devolvidas ao navegador.
    Quando houver uma API oficial da casa integrada, o saldo e as apostas abertas
    podem ser atualizados em tempo real aqui.
    """
    connected = os.getenv("BET_ACCOUNT_CONNECTED", "false").strip().lower() in ("1", "true", "yes", "sim")
    house = os.getenv("BET_HOUSE_NAME", "NÃO CONFIGURADA").strip()
    user = os.getenv("BET_ACCOUNT_USER", "").strip()
    account_id = os.getenv("BET_ACCOUNT_ID", "").strip()
    mode = os.getenv("BET_ACCOUNT_MODE", "SIMULACAO").strip().upper()
    currency = os.getenv("BET_ACCOUNT_CURRENCY", "BRL").strip().upper()

    def env_float(name):
        raw = os.getenv(name, "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except Exception:
            return None

    balance = env_float("BET_ACCOUNT_BALANCE")
    available = env_float("BET_ACCOUNT_AVAILABLE")
    open_bets = os.getenv("BET_ACCOUNT_OPEN_BETS", "").strip()
    try:
        open_bets = int(open_bets) if open_bets else 0
    except Exception:
        open_bets = 0

    return {
        "conectada": connected,
        "status": "CONECTADA" if connected else "AGUARDANDO API",
        "casa": house,
        "usuario": _mask(user, 2, 2) if user else "-",
        "id_conta": _mask(account_id, 2, 2) if account_id else "-",
        "modo": mode,
        "moeda": currency,
        "saldo": balance,
        "saldo_disponivel": available,
        "apostas_abertas": open_bets,
        "observacao": (
            "Dados em tempo real pela API oficial da casa."
            if connected
            else "A conta ainda não está conectada à API oficial da casa de apostas."
        ),
    }


app = FastAPI(title="MATRIX - FUTEBOL")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def agora():
    return datetime.now(TZ)


def token():
    value = os.getenv("SPORTMONKS_TOKEN", "").strip()
    if not value:
        raise RuntimeError("SPORTMONKS_TOKEN não configurado no Render.")
    return value


def api_get(path, params=None):
    p = dict(params or {})
    p["api_token"] = token()
    r = requests.get(
        BASE + path,
        params=p,
        timeout=35,
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


def get_pages(path, params=None, max_pages=12):
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
        if not data or not pagination or pagination.get("has_more") is False:
            break
        page += 1
    return out


def parse_dt(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ)
    except Exception:
        return None


def participants(f):
    home = {"id": None, "name": "Casa"}
    away = {"id": None, "name": "Fora"}

    for p in f.get("participants") or []:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        item = {"id": p.get("id"), "name": p.get("name") or "Time"}
        if loc == "home":
            home = item
        elif loc == "away":
            away = item

    if home["name"] == "Casa" or away["name"] == "Fora":
        raw = str(f.get("name") or "")
        for sep in (" vs ", " v ", " - "):
            if sep in raw:
                a, b = raw.split(sep, 1)
                if home["name"] == "Casa":
                    home["name"] = a.strip()
                if away["name"] == "Fora":
                    away["name"] = b.strip()
                break

    return home, away


def league_obj(f):
    return f.get("league") or {}


def league_name(f):
    return str(league_obj(f).get("name") or f.get("league_id") or "Liga")


def country_name(f):
    league = league_obj(f)
    country = league.get("country") or {}
    return str(country.get("name") or league.get("country_name") or "").strip()


def is_libertadores(f):
    return "libertadores" in league_name(f).lower()


def is_brazilian(f):
    country = country_name(f).lower()
    if country:
        return country in ("brazil", "brasil")
    name = league_name(f).lower()
    terms = (
        "brasileir", "série a", "serie a", "série b", "serie b",
        "copa do brasil", "paulista", "carioca", "mineiro",
        "gaúcho", "gaucho", "paranaense", "baiano", "pernambucano",
        "cearense", "catarinense", "goiano"
    )
    return any(t in name for t in terms)


def is_international(f):
    if is_libertadores(f):
        return True
    # Qualquer liga não identificada claramente como brasileira entra em "Internacionais".
    return not is_brazilian(f)


def kickoff_text(f):
    dt = parse_dt(f.get("starting_at"))
    return dt.strftime("%d/%m/%Y %H:%M") if dt else str(f.get("starting_at") or "-")


def starts_in(f):
    dt = parse_dt(f.get("starting_at"))
    if not dt:
        return "-"
    seconds = int((dt - agora()).total_seconds())
    if seconds <= 0:
        return "iniciado/encerrado"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"em {days}d {hours}h"
    if hours:
        return f"em {hours}h {mins}min"
    return f"em {max(0, mins)}min"


def current_score(f):
    current = {}
    fallback = {}
    for s in f.get("scores") or []:
        score = s.get("score") or {}
        loc = str(score.get("participant") or "").lower()
        goals = score.get("goals")
        if loc not in ("home", "away") or goals is None:
            continue
        fallback[loc] = goals
        if str(s.get("description") or "").upper() == "CURRENT":
            current[loc] = goals

    data = current if "home" in current and "away" in current else fallback
    if "home" not in data or "away" not in data:
        return "-"
    return f"{data['home']} x {data['away']}"


def live_minute(f):
    ticking = []
    any_period = []
    for p in f.get("periods") or []:
        mins = p.get("minutes")
        secs = p.get("seconds")
        if isinstance(mins, (int, float)):
            item = (int(mins), int(secs or 0), bool(p.get("ticking")))
            any_period.append(item)
            if p.get("ticking"):
                ticking.append(item)

    source = ticking or any_period
    if source:
        mins, secs, _ = max(source, key=lambda x: (x[0], x[1]))
        return f"{mins}:{secs:02d}", False

    # Fallback aproximado se o plano não entregar periods/minutes.
    dt = parse_dt(f.get("starting_at"))
    if not dt:
        return "-", True
    elapsed = int((agora() - dt).total_seconds() // 60)
    if elapsed < 0:
        return "-", True
    approx = elapsed if elapsed <= 55 else elapsed - 15
    approx = max(0, min(120, approx))
    return f"~{approx}'", True


def state_text(f):
    st = f.get("state") or {}
    return str(st.get("short_name") or st.get("state") or st.get("name") or "AO VIVO")


def upcoming():
    start = agora().date()
    end = (agora() + timedelta(days=CONFIG["dias_busca"])).date()
    rows = get_pages(
        f"/fixtures/between/{start.isoformat()}/{end.isoformat()}",
        {"include": "participants;league.country;state"},
        max_pages=12,
    )
    seen, out = set(), []
    for f in rows:
        fid = f.get("id")
        if fid in seen:
            continue
        seen.add(fid)
        out.append(f)
    return out


def live_games():
    payload = api_get(
        "/livescores/inplay",
        {"include": "participants;league.country;state;scores;periods"},
    )
    return payload.get("data", []) if isinstance(payload, dict) else []


def prematch_odds(fid):
    return get_pages(
        f"/odds/pre-match/fixtures/{fid}",
        {"include": "market;bookmaker"},
        max_pages=10,
    )


def live_odds(fid):
    try:
        payload = api_get(
            f"/odds/inplay/fixtures/{fid}",
            {"include": "market;bookmaker"},
        )
        return payload.get("data", []) if isinstance(payload, dict) else [], None
    except Exception as e:
        return [], str(e)


def normalize_label(raw):
    x = str(raw or "").strip().upper()
    return {
        "1": "HOME", "HOME": "HOME", "CASA": "HOME", "LOCAL": "HOME",
        "X": "DRAW", "DRAW": "DRAW", "EMPATE": "DRAW",
        "2": "AWAY", "AWAY": "AWAY", "FORA": "AWAY", "VISITANTE": "AWAY",
    }.get(x)


def parse_1x2(rows):
    buckets = {"HOME": [], "DRAW": [], "AWAY": []}
    for o in rows:
        market = o.get("market") or {}
        desc = str(
            o.get("market_description")
            or market.get("name")
            or market.get("developer_name")
            or ""
        ).upper()

        if not (
            "FULLTIME RESULT" in desc
            or "FULL TIME RESULT" in desc
            or "MATCH WINNER" in desc
            or "1X2" in desc
            or "3 WAY" in desc
            or "3-WAY" in desc
            or o.get("market_id") in (1, 52, 856)
        ):
            continue

        key = normalize_label(
            o.get("label") or o.get("name") or o.get("selection") or o.get("value_label")
        )
        if not key:
            continue

        try:
            odd = float(o.get("value"))
        except Exception:
            continue
        if odd > 1.0:
            buckets[key].append(odd)

    out = {}
    for key, vals in buckets.items():
        if vals:
            med = statistics.median(vals)
            out[key] = {"odd": med, "best": max(vals), "n": len(vals)}

    total = sum(1 / v["odd"] for v in out.values()) or 1
    for v in out.values():
        v["market_prob"] = (1 / v["odd"]) / total
    return out


def h2h_score_by_team(f):
    by_team = {}
    current_found = False

    for s in f.get("scores") or []:
        pid = s.get("participant_id")
        score = s.get("score") or {}
        goals = score.get("goals")
        if pid is None or goals is None:
            continue
        if str(s.get("description") or "").upper() == "CURRENT":
            by_team[pid] = int(goals)
            current_found = True

    if current_found and len(by_team) >= 2:
        return by_team

    # Fallback por localização.
    home, away = participants(f)
    loc_to_id = {"home": home["id"], "away": away["id"]}
    by_team = {}
    for s in f.get("scores") or []:
        score = s.get("score") or {}
        loc = str(score.get("participant") or "").lower()
        goals = score.get("goals")
        pid = s.get("participant_id") or loc_to_id.get(loc)
        if pid is not None and goals is not None:
            by_team[pid] = int(goals)
    return by_team


def h2h_history(team1_id, team2_id, team1_name, team2_name):
    if not team1_id or not team2_id:
        return {
            "disponivel": False,
            "motivo": "IDs dos times não disponíveis no feed.",
            "jogos": 0,
            "ultimos": [],
        }

    key = tuple(sorted((int(team1_id), int(team2_id))))
    cached = H2H_CACHE.get(key)
    if cached and time.time() - cached["ts"] < H2H_TTL:
        return cached["data"]

    try:
        rows = get_pages(
            f"/fixtures/head-to-head/{team1_id}/{team2_id}",
            {"include": "participants;scores;state"},
            max_pages=3,
        )
    except Exception as e:
        data = {
            "disponivel": False,
            "motivo": str(e),
            "jogos": 0,
            "ultimos": [],
        }
        H2H_CACHE[key] = {"ts": time.time(), "data": data}
        return data

    def sort_key(f):
        dt = parse_dt(f.get("starting_at"))
        return dt.timestamp() if dt else 0

    rows = sorted(rows, key=sort_key, reverse=True)
    valid = []

    for f in rows:
        dt = parse_dt(f.get("starting_at"))
        if dt and dt >= agora():
            continue

        scores = h2h_score_by_team(f)
        if team1_id not in scores or team2_id not in scores:
            continue

        g1, g2 = scores[team1_id], scores[team2_id]
        if g1 > g2:
            winner = "TEAM1"
        elif g2 > g1:
            winner = "TEAM2"
        else:
            winner = "DRAW"

        valid.append({
            "data": dt.strftime("%d/%m/%Y") if dt else "-",
            "jogo": f.get("name") or f"{team1_name} x {team2_name}",
            "placar_time1": g1,
            "placar_time2": g2,
            "placar": f"{g1} x {g2}",
            "vencedor": winner,
            "gols": g1 + g2,
        })
        if len(valid) >= CONFIG["h2h_jogos"]:
            break

    n = len(valid)
    if not n:
        data = {
            "disponivel": False,
            "motivo": "Nenhum confronto anterior com placar disponível no seu plano.",
            "jogos": 0,
            "ultimos": [],
        }
    else:
        w1 = sum(1 for x in valid if x["vencedor"] == "TEAM1")
        w2 = sum(1 for x in valid if x["vencedor"] == "TEAM2")
        draws = n - w1 - w2
        avg_goals = sum(x["gols"] for x in valid) / n
        over15 = sum(1 for x in valid if x["gols"] >= 2)
        btts = sum(
            1 for x in valid
            if x["placar_time1"] > 0 and x["placar_time2"] > 0
        )

        # Laplace smoothing evita 100% artificial com poucos jogos.
        probs = {
            "HOME": (w1 + 1) / (n + 3),
            "DRAW": (draws + 1) / (n + 3),
            "AWAY": (w2 + 1) / (n + 3),
        }

        tendency = max(probs, key=probs.get)
        tendency_name = {
            "HOME": team1_name,
            "DRAW": "Empate",
            "AWAY": team2_name,
        }[tendency]

        data = {
            "disponivel": True,
            "motivo": None,
            "jogos": n,
            "vitorias_time1": w1,
            "empates": draws,
            "vitorias_time2": w2,
            "media_gols": round(avg_goals, 2),
            "over15_pct": round(over15 / n * 100, 1),
            "ambas_marcam_pct": round(btts / n * 100, 1),
            "tendencia": tendency_name,
            "probs": probs,
            "ultimos": valid,
        }

    H2H_CACHE[key] = {"ts": time.time(), "data": data}
    return data


def base_item(f, live=False):
    home, away = participants(f)
    minute, approximate = live_minute(f) if live else ("-", False)
    return {
        "fixture_id": f.get("id"),
        "jogo": f"{home['name']} x {away['name']}",
        "casa": home["name"],
        "fora": away["name"],
        "casa_id": home["id"],
        "fora_id": away["id"],
        "liga": league_name(f),
        "pais": country_name(f) or "não informado",
        "horario": kickoff_text(f),
        "start_time_iso": (parse_dt(f.get("starting_at")).isoformat() if parse_dt(f.get("starting_at")) else str(f.get("starting_at") or "")),
        "comeca_em": starts_in(f) if not live else None,
        "libertadores": is_libertadores(f),
        "internacional": is_international(f),
        "ao_vivo": live,
        "placar": current_score(f) if live else None,
        "estado": state_text(f) if live else None,
        "tempo_jogo": minute if live else None,
        "tempo_aproximado": approximate if live else False,
    }


def analyze_market(f, rows, live=False, odds_error=None):
    item = base_item(f, live)
    market = parse_1x2(rows)

    if not market:
        item.update({
            "status": "ODDS AO VIVO INDISPONÍVEIS" if live and odds_error else "SEM 1X2",
            "motivo": odds_error or "Partida encontrada, mas sem mercado 1X2 disponível.",
            "h2h": {"disponivel": False, "jogos": 0, "ultimos": []},
        })
        return item, None

    h2h = h2h_history(
        item["casa_id"], item["fora_id"], item["casa"], item["fora"]
    )

    # Combina mercado + histórico direto. H2H tem peso menor para não dominar
    # a análise quando a amostra é pequena.
    h2h_weight = 0.30 if h2h.get("jogos", 0) >= 3 else (0.15 if h2h.get("jogos", 0) else 0.0)
    market_weight = 1.0 - h2h_weight

    scored = {}
    for key, value in market.items():
        hist_prob = (h2h.get("probs") or {}).get(key, value["market_prob"])
        combined = market_weight * value["market_prob"] + h2h_weight * hist_prob
        scored[key] = {**value, "hist_prob": hist_prob, "combined": combined}

    selection, v = max(scored.items(), key=lambda x: x[1]["combined"])
    pick = {
        "HOME": item["casa"],
        "DRAW": "Empate",
        "AWAY": item["fora"],
    }[selection]

    reasons = []
    if not (CONFIG["odd_min"] <= v["odd"] <= CONFIG["odd_max"]):
        reasons.append(
            f"odd {v['odd']:.2f} fora de {CONFIG['odd_min']:.2f}–{CONFIG['odd_max']:.2f}"
        )
    if v["combined"] < CONFIG["prob_min"]:
        reasons.append(
            f"índice combinado {v['combined']*100:.1f}% abaixo de {CONFIG['prob_min']*100:.0f}%"
        )

    approved = not reasons
    stake = CONFIG["stake"]
    potential_return = stake * v["odd"]
    potential_profit = potential_return - stake

    item.update({
        "mercado": "Resultado da partida (1X2)",
        "selecao": pick,
        "codigo_selecao": selection,
        "odd": round(v["odd"], 2),
        "melhor_odd": round(v["best"], 2),
        "casas": v["n"],
        "prob_mercado": round(v["market_prob"] * 100, 1),
        "indice_combinado": round(v["combined"] * 100, 1),
        "peso_h2h": round(h2h_weight * 100, 0),
        "stake_padrao": round(stake, 2),
        "retorno_potencial_padrao": round(potential_return, 2),
        "lucro_potencial_padrao": round(potential_profit, 2),
        "h2h": h2h,
        "status": "APROVADO" if approved else "AGUARDAR",
        "motivo": "Passou pelos filtros de odds + histórico H2H." if approved else "; ".join(reasons),
    })

    return item, item if approved else None


def run_analysis():
    with LOCK:
        STATE["status"] = "analisando"
        STATE["erro"] = None

    try:
        futures = upcoming()
        lives = live_games()

        todos = []
        sinais = []
        with_odds = 0
        analyzed = 0

        # Evita uma explosão de chamadas caso o plano retorne milhares de partidas.
        futures = futures[:180]

        for f in futures:
            if not f.get("has_odds"):
                item = base_item(f, False)
                item.update({
                    "status": "SEM ODDS",
                    "motivo": "A SportMonks informou que esta partida ainda não possui odds.",
                    "h2h": {"disponivel": False, "jogos": 0, "ultimos": []},
                })
                todos.append(item)
                continue

            with_odds += 1
            try:
                rows = prematch_odds(f.get("id"))
                err = None
            except Exception as e:
                rows, err = [], str(e)

            item, signal = analyze_market(f, rows, live=False, odds_error=err)
            if item.get("odd") is not None:
                analyzed += 1
            todos.append(item)
            if signal:
                sinais.append(signal)

        live_items = []
        for f in lives:
            rows, err = live_odds(f.get("id"))
            item, signal = analyze_market(f, rows, live=True, odds_error=err)
            live_items.append(item)
            if signal:
                signal = dict(signal)
                signal["tipo_sinal"] = "AO VIVO"
                sinais.append(signal)

        libertadores = [x for x in todos if x.get("libertadores")]
        internacionais = [x for x in todos if x.get("internacional")]

        with LOCK:
            STATE.update({
                "status": "online",
                "ultima_atualizacao": agora().isoformat(timespec="seconds"),
                "jogos_encontrados": len(futures),
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



def _betfair_selection_name(signal):
    """
    With SportMonksFixtureId, Bf Bot Manager can resolve HOME/AWAY to the
    correct Betfair team selection near event start.
    For draw, use Betfair's static selection name.
    """
    code = str(signal.get("codigo_selecao") or "").upper()
    if code == "HOME":
        return "HOME"
    if code == "AWAY":
        return "AWAY"
    if code == "DRAW" or str(signal.get("selecao") or "").strip().lower() == "empate":
        return "The Draw"
    return str(signal.get("selecao") or "").strip()


def _minutes_until_signal(signal):
    raw = signal.get("start_time_iso")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return int((dt.astimezone(TZ) - agora()).total_seconds() // 60)
    except Exception:
        return None


def bfbot_tips():
    """
    Returns pre-match approved tips only.
    Live tips are intentionally excluded from the CSV URL because Bf Bot
    Manager's web-location importer is designed around scheduled reloading,
    not second-by-second in-play execution.
    """
    if not CONFIG["bfbot_enabled"]:
        return []

    with LOCK:
        signals = list(STATE.get("sinais") or [])

    rows = []
    seen = set()

    for s in signals:
        if s.get("ao_vivo"):
            continue
        if s.get("status") != "APROVADO":
            continue
        if not s.get("selecao") or not s.get("fixture_id"):
            continue

        mins = _minutes_until_signal(s)
        # Keep the tip available until kickoff. This is essential because
        # Bf Bot Manager resolves SportMonksFixtureId to Betfair IDs only close
        # to event start (typically ~30 minutes before kickoff).
        if mins is not None and mins < CONFIG["bfbot_min_minutes_before_start"]:
            continue

        event_key = (s.get("fixture_id"), s.get("codigo_selecao"))
        if event_key in seen:
            continue
        seen.add(event_key)

        selection = _betfair_selection_name(s)
        if not selection:
            continue

        rows.append({
            "Provider": CONFIG["bfbot_provider"],
            "SportMonksFixtureId": str(s.get("fixture_id") or ""),
            "SelectionName": selection,
            "MarketType": "MATCH_ODDS",
            "BetType": "BACK",
            "Size": f"{float(s.get('stake_padrao') or CONFIG['stake']):.2f}",
            "BSP": "false",
            "EventName": str(s.get("jogo") or ""),
        })

        if len(rows) >= CONFIG["bfbot_max_tips"]:
            break

    return rows


def bfbot_csv_text():
    fields = ["Provider", "SportMonksFixtureId", "SelectionName", "MarketType", "BetType", "Size", "BSP", "EventName"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in bfbot_tips():
        writer.writerow(row)
    return buf.getvalue()



def worker():
    while True:
        run_analysis()
        time.sleep(CONFIG["intervalo"])


@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/status")
def status():
    # Copia o estado rapidamente e libera o lock antes de calcular o feed BFBOT.
    # Isso evita o travamento que deixava o painel em "..." e todos os contadores em 0.
    with LOCK:
        state_copy = dict(STATE)

    tips = bfbot_tips()

    return JSONResponse({
        "nome": "MATRIX - FUTEBOL",
        "versao": "V3.5.4 BFBOT SPORTMONKS 30MIN FIX + BSP OFF",
        "config": CONFIG,
        "conta": account_info(),
        "bfbot": {
            "habilitado": CONFIG["bfbot_enabled"],
            "provider": CONFIG["bfbot_provider"],
            "tips_prontas": len(tips),
            "market_type": "MATCH_ODDS",
            "bet_type": "BACK",
            "minutos_antes": CONFIG["bfbot_min_minutes_before_start"],
            "feed_path": "/bfbot/tips.csv",
            "sportmonks_fixture_id": True,
            "bsp": False,
            "modo": "FEED PARA BFBOT MANAGER",
        },
        **state_copy,
    })


@app.post("/api/analisar")
def analisar():
    run_analysis()
    return status()



@app.get("/api/account")
def api_account():
    return JSONResponse(account_info())



@app.get("/bfbot/tips.csv", response_class=PlainTextResponse)
def bfbot_feed():
    return PlainTextResponse(
        bfbot_csv_text(),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/bfbot")
def bfbot_status():
    tips = bfbot_tips()
    return JSONResponse({
        "habilitado": CONFIG["bfbot_enabled"],
        "provider": CONFIG["bfbot_provider"],
        "tips_prontas": len(tips),
        "feed_path": "/bfbot/tips.csv",
        "sportmonks_fixture_id": True,
        "bsp": False,
        "market_type": "MATCH_ODDS",
        "bet_type": "BACK",
        "minutos_antes": CONFIG["bfbot_min_minutes_before_start"],
        "tips": tips,
    })


@app.get("/health")
def health():
    return {"ok": True, "versao": "3.5.4"}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))
