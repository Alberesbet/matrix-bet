import os, time, threading, statistics, csv, io, re, unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, Request
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
    # Quando IP/InPlay não vier no CSV do BF Bot Manager, Match Odds é
    # considerado "provável ao vivo" somente dentro desta janela.
    "betfair_live_max_minutes": int(os.getenv("BETFAIR_LIVE_MAX_MINUTES", "115")),
    # Odds/volumes vindos de CSV mais antigo que isto são marcados como desatualizados.
    "betfair_visible_fresh_seconds": int(os.getenv("BETFAIR_VISIBLE_FRESH_SECONDS", "120")),
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

BETFAIR_MIRROR = {
    "markets": [],
    "updated_at": None,
    "filename": None,
    "rows_received": 0,
    "error": None,
}

BETFAIR_VISIBLE = {
    "rows": [],
    "updated_at": None,
    "filename": None,
    "rows_received": 0,
    "error": None,
}

BETFAIR_VISIBLE_CACHE_FILE = Path(
    os.getenv("BETFAIR_VISIBLE_CACHE_FILE", "/tmp/matrix_betfair_visible.csv")
)

BETFAIR_MARKETS_CACHE_FILE = Path(
    os.getenv("BETFAIR_MARKETS_CACHE_FILE", "/tmp/matrix_betfair_markets.csv")
)

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



def _norm_text(value):
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _event_pair(value):
    text = str(value or "").strip()
    for sep in (" v ", " vs ", " x ", " - "):
        if sep in text:
            a, b = text.split(sep, 1)
            return _norm_text(a), _norm_text(b)
    return _norm_text(text), ""


def _find_matrix_game(event_name):
    a, b = _event_pair(event_name)
    if not a:
        return None

    with LOCK:
        pool = (
            list(STATE.get("ao_vivo") or [])
            + list(STATE.get("sinais") or [])
            + list(STATE.get("todos") or [])
        )

    best = None
    for item in pool:
        ia = _norm_text(item.get("casa"))
        ib = _norm_text(item.get("fora"))
        if a == ia and b == ib:
            return item
        if a == ib and b == ia:
            return item

        # fallback conservador para diferenças pequenas como FC/IF
        if b and ia and ib:
            score = 0
            if a in ia or ia in a:
                score += 1
            if b in ib or ib in b:
                score += 1
            if score == 2:
                best = item
    return best


def _row_get(row, *names):
    normalized = {_norm_text(k).replace(" ", ""): v for k, v in row.items()}
    for name in names:
        key = _norm_text(name).replace(" ", "")
        if key in normalized:
            return str(normalized[key] or "").strip()
    return ""


def parse_betfair_markets_csv(text):
    text = str(text or "").lstrip("\ufeff").strip()
    if not text:
        return []

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delim = dialect.delimiter
    except Exception:
        delim = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    out = []
    seen = set()

    for raw in reader:
        if not raw:
            continue

        event_name = _row_get(
            raw, "EventName", "Event Name", "Evento", "Evento/mercado", "Event"
        )
        market_name = _row_get(
            raw, "MarketName", "Market Name", "Mercado", "Market"
        )
        event_id = _row_get(raw, "EventId", "Event ID", "ID do evento")
        market_id = _row_get(raw, "MarketId", "Market ID", "ID do mercado")
        start_time = _row_get(
            raw, "StartTime", "Start Time", "Hora de inicio", "Hora de início"
        )
        total_matched = _row_get(
            raw, "TotalMatched", "Total Matched", "Montante Correspondido"
        )
        status = _row_get(raw, "Status", "Estado")
        in_play = _row_get(raw, "InPlay", "In Play", "IP")

        if not event_name and not market_id:
            continue

        key = market_id or f"{event_name}|{market_name}|{start_time}"
        if key in seen:
            continue
        seen.add(key)

        matrix = _find_matrix_game(event_name)
        item = {
            "event_name": event_name or "-",
            "event_id": event_id or None,
            "market_name": market_name or "Mercado Betfair",
            "market_id": market_id or None,
            "start_time": start_time or None,
            "total_matched": total_matched or None,
            "status": status or "IMPORTADO",
            "in_play": str(in_play).strip().lower() in ("1", "true", "yes", "sim", "in-play", "in play"),
            "linkado_matrix": bool(matrix),
        }

        if matrix:
            item.update({
                "fixture_id": matrix.get("fixture_id"),
                "matrix_status": matrix.get("status"),
                "matrix_live": bool(matrix.get("ao_vivo")),
                "placar": matrix.get("placar"),
                "tempo_jogo": matrix.get("tempo_jogo"),
                "liga": matrix.get("liga"),
                "pais": matrix.get("pais"),
                "selecao": matrix.get("selecao"),
                "odd": matrix.get("odd"),
                "indice_combinado": matrix.get("indice_combinado"),
                "motivo": matrix.get("motivo"),
            })
        out.append(item)

    return out




def _parse_br_number(value):
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace("R$", "").replace("%", "").strip()
    s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return None


def _parse_first_favorite(value):
    # Ex.: Sabah FA, R$515,77@2,32
    s = str(value or "").strip()
    if not s:
        return None, None, None
    if "@" not in s:
        return s, None, None
    left, odd_raw = s.rsplit("@", 1)
    odd = _parse_br_number(odd_raw)
    selection = left.strip()
    amount = None
    m = re.match(r"^(.*?),\s*R\$\s*([0-9\.\,]+)\s*$", left)
    if m:
        selection = m.group(1).strip()
        amount = _parse_br_number(m.group(2))
    return selection, odd, amount


def _split_event_market(value):
    s = str(value or "").strip()
    if "\\" in s:
        return s.split("\\", 1)
    return s, ""


def _market_lookup_indexes():
    with LOCK:
        markets = list(BETFAIR_MIRROR.get("markets") or [])
    exact, relaxed = {}, {}
    for m in markets:
        e = _norm_text(m.get("event_name"))
        mk = _norm_text(m.get("market_name"))
        st = str(m.get("start_time") or "").strip()
        exact[(e, mk, st)] = m
        relaxed[(e, mk)] = m
    return exact, relaxed


def parse_betfair_visible_csv(text):
    """
    Parser do arquivo REAL:
    BF Bot Manager -> Exportar todos os dados visíveis.
    """
    text = str(text or "").lstrip("\ufeff").strip()
    if not text:
        return []

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t")
        delim = dialect.delimiter
    except Exception:
        delim = ";"

    exact, relaxed = _market_lookup_indexes()
    out, seen = [], set()

    for raw in csv.DictReader(io.StringIO(text), delimiter=delim):
        if not raw:
            continue

        combined = _row_get(raw, "Evento/mercado", "Evento / mercado")
        event_name, market_name = _split_event_market(combined)

        if not event_name:
            event_name = _row_get(raw, "EventName", "Event Name", "Evento")
        if not market_name:
            market_name = _row_get(raw, "MarketName", "Market Name", "Mercado")

        start_time = _row_get(raw, "Hora de início", "Hora de inicio", "StartTime", "Start Time")
        status = _row_get(raw, "Status", "Estado")
        ip_raw = _row_get(raw, "IP", "InPlay", "In Play")
        placar = _row_get(raw, "Placar ao vivo", "Placar")
        tempo = _row_get(raw, "Tempo", "Game Time")
        video = _row_get(raw, "Vídeo ao vivo", "Video ao vivo", "Live Video")
        favorito_raw = _row_get(raw, "1º favorito", "1o favorito", "Primeiro favorito")
        total = _row_get(raw, "Total correspondido", "TotalMatched", "Total Matched")
        back_book = _row_get(raw, "Back book %", "Back Book %")
        lay_book = _row_get(raw, "Lay book %", "Lay Book %")

        if not event_name:
            continue

        favorito, favorite_odd, favorite_amount = _parse_first_favorite(favorito_raw)

        key = (_norm_text(event_name), _norm_text(market_name), start_time)
        if key in seen:
            continue
        seen.add(key)

        mirror = exact.get(key)
        if mirror is None:
            mirror = relaxed.get((_norm_text(event_name), _norm_text(market_name)))

        matrix = _find_matrix_game(event_name)

        item = {
            "event_name": event_name,
            "market_name": market_name or "Mercado Betfair",
            "start_time": start_time or None,
            "status": status or "VISÍVEL",
            "in_play": str(ip_raw or "").strip().lower() in (
                "1", "true", "yes", "sim", "checked", "in-play", "in play"
            ),
            "in_play_raw": ip_raw or None,
            "placar": placar or None,
            "tempo_jogo": tempo or None,
            "video_ao_vivo": video or None,
            "favorite_selection": favorito or None,
            "favorite_odd": favorite_odd,
            "favorite_amount": favorite_amount,
            "total_matched": total or None,
            "total_matched_num": _parse_br_number(total),
            "back_book": back_book or None,
            "lay_book": lay_book or None,
            "market_id": (mirror or {}).get("market_id"),
            "event_id": (mirror or {}).get("event_id"),
            "linkado_marketid": bool((mirror or {}).get("market_id")),
            "linkado_matrix": bool(matrix),
        }

        if matrix:
            item.update({
                "fixture_id": matrix.get("fixture_id"),
                "matrix_status": matrix.get("status"),
                "matrix_live": bool(matrix.get("ao_vivo")),
                "liga": matrix.get("liga"),
                "pais": matrix.get("pais"),
                "selecao": matrix.get("selecao"),
                "odd": matrix.get("odd"),
                "indice_combinado": matrix.get("indice_combinado"),
                "motivo": matrix.get("motivo"),
            })

        out.append(item)

    return out


def _save_betfair_visible_cache(text):
    try:
        BETFAIR_VISIBLE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BETFAIR_VISIBLE_CACHE_FILE.write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass


def _load_betfair_visible_cache():
    try:
        if not BETFAIR_VISIBLE_CACHE_FILE.exists():
            return
        text = BETFAIR_VISIBLE_CACHE_FILE.read_text(encoding="utf-8")
        rows = parse_betfair_visible_csv(text)
        if not rows:
            return
        with LOCK:
            BETFAIR_VISIBLE["rows"] = rows
            BETFAIR_VISIBLE["updated_at"] = datetime.now(TZ).isoformat()
            BETFAIR_VISIBLE["filename"] = BETFAIR_VISIBLE_CACHE_FILE.name
            BETFAIR_VISIBLE["rows_received"] = len(rows)
            BETFAIR_VISIBLE["error"] = None
    except Exception as e:
        with LOCK:
            BETFAIR_VISIBLE["error"] = str(e)


def _market_is_match_odds(market):
    name = _norm_text(market.get("market_name"))
    return (
        "match odds" in name
        or "resultado da partida" in name
        or name in ("1 x 2", "1x2")
        or not name
        or name == "mercado betfair"
    )


def _flex_start_dt(raw):
    s = str(raw or "").strip()
    if not s:
        return None

    # ISO / YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ)
    except Exception:
        pass

    # DD-MM HH:MM, formato comum da grade
    m = re.match(r"^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$", s)
    if m:
        now = agora()
        return datetime(
            now.year, int(m.group(2)), int(m.group(1)),
            int(m.group(3)), int(m.group(4)),
            tzinfo=TZ
        )

    # DD/MM/YYYY HH:MM:SS, formato do Exportar mercados
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$", s)
    if m:
        return datetime(
            int(m.group(3)), int(m.group(2)), int(m.group(1)),
            int(m.group(4)), int(m.group(5)), int(m.group(6) or 0),
            tzinfo=TZ
        )
    return None


def _signal_event_names(signal):
    home = str(signal.get("casa") or "").strip()
    away = str(signal.get("fora") or "").strip()
    return _norm_text(home), _norm_text(away)


def _market_event_names(market):
    return _event_pair(market.get("event_name"))


def _find_betfair_market_for_signal(signal):
    """
    Liga um sinal SportMonks/MATRIX ao mercado Betfair importado do BF Bot Manager.
    Requer MarketId real. Faz match principalmente por Casa/Fora e, quando houver,
    usa o horário para desempatar.
    """
    sh, sa = _signal_event_names(signal)
    if not sh or not sa:
        return None

    with LOCK:
        markets = list(BETFAIR_MIRROR.get("markets") or [])

    candidates = []
    for m in markets:
        market_id = str(m.get("market_id") or "").strip()
        if not market_id:
            continue
        if not _market_is_match_odds(m):
            continue

        mh, ma = _market_event_names(m)
        exact = (sh == mh and sa == ma)
        reversed_order = (sh == ma and sa == mh)

        # fallback conservador para FC/IF e abreviações pequenas
        fuzzy = False
        if mh and ma:
            fuzzy = (
                (sh in mh or mh in sh) and
                (sa in ma or ma in sa)
            )

        if not (exact or reversed_order or fuzzy):
            continue

        score = 100 if exact else (80 if reversed_order else 60)

        signal_dt = _flex_start_dt(signal.get("start_time_iso"))
        market_dt = _flex_start_dt(m.get("start_time"))
        delta = None
        if signal_dt and market_dt:
            delta = abs((signal_dt - market_dt).total_seconds())
            if delta <= 15 * 60:
                score += 30
            elif delta <= 60 * 60:
                score += 10
            elif delta > 6 * 60 * 60:
                score -= 40

        candidates.append((score, delta if delta is not None else 10**12, m))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    best = candidates[0]

    # Não usamos matches fracos para aposta.
    if best[0] < 60:
        return None
    return best[2]


def _save_betfair_markets_cache(text):
    try:
        BETFAIR_MARKETS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BETFAIR_MARKETS_CACHE_FILE.write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass


def _load_betfair_markets_cache():
    try:
        if not BETFAIR_MARKETS_CACHE_FILE.exists():
            return
        text = BETFAIR_MARKETS_CACHE_FILE.read_text(encoding="utf-8")
        markets = parse_betfair_markets_csv(text)
        if not markets:
            return
        with LOCK:
            BETFAIR_MIRROR["markets"] = markets
            BETFAIR_MIRROR["updated_at"] = datetime.now(TZ).isoformat()
            BETFAIR_MIRROR["filename"] = BETFAIR_MARKETS_CACHE_FILE.name
            BETFAIR_MIRROR["rows_received"] = len(markets)
            BETFAIR_MIRROR["error"] = None
    except Exception as e:
        with LOCK:
            BETFAIR_MIRROR["error"] = str(e)



def _status_is_liveish(market):
    status = _norm_text(market.get("status"))
    return status in (
        "open", "aberto", "in play", "inplay", "ao vivo",
        "suspended", "suspenso"
    )



def _iso_age_seconds(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return max(0, int((agora() - dt.astimezone(TZ)).total_seconds()))
    except Exception:
        return None


def betfair_visible_age_seconds():
    with LOCK:
        updated = BETFAIR_VISIBLE.get("updated_at")
    return _iso_age_seconds(updated)


def betfair_visible_is_fresh():
    age = betfair_visible_age_seconds()
    return age is not None and age <= CONFIG["betfair_visible_fresh_seconds"]


def _market_live_state(market):
    """
    CONFIRMADO: IP/InPlay explícito ou SportMonks.
    PROVAVEL_AO_VIVO: status OPEN/SUSPENDED + horário já passou.
    O CSV real recebido deixa IP, Tempo e Placar vazios.
    """
    if market.get("in_play") or market.get("matrix_live"):
        return "CONFIRMADO"

    dt = _flex_start_dt(market.get("start_time"))
    if not dt:
        return None

    delta_min = (agora() - dt).total_seconds() / 60.0
    if delta_min < 0:
        return None

    status = _norm_text(market.get("status"))
    if status in ("open", "aberto", "suspended", "suspenso") and delta_min <= CONFIG["betfair_live_max_minutes"]:
        return "PROVAVEL_AO_VIVO"

    return None


def _betfair_live_source():
    with LOCK:
        visible = list(BETFAIR_VISIBLE.get("rows") or [])
        mirror = list(BETFAIR_MIRROR.get("markets") or [])
    return visible if visible else mirror


def betfair_live_markets(markets=None):
    if markets is None:
        markets = _betfair_live_source()

    out = []
    seen = set()
    for m in markets:
        state = _market_live_state(m)
        if not state:
            continue

        # Avoid showing every market of the same match in AO VIVO.
        # Prefer Result/Match Odds; otherwise one representative market per event.
        event_key = str(m.get("event_id") or _norm_text(m.get("event_name"))).strip()
        if not event_key:
            continue

        if event_key in seen:
            # If current representative is not match odds but this one is,
            # replace it later by rebuilding below.
            continue
        seen.add(event_key)

        item = dict(m)
        item["live_source"] = state
        item["ao_vivo"] = True
        out.append(item)

    # Second pass: where possible, replace each event with its Match Odds market.
    by_event = {}
    for m in markets:
        state = _market_live_state(m)
        if not state:
            continue
        event_key = str(m.get("event_id") or _norm_text(m.get("event_name"))).strip()
        if not event_key:
            continue
        current = by_event.get(event_key)
        if current is None or (_market_is_match_odds(m) and not _market_is_match_odds(current)):
            item = dict(m)
            item["live_source"] = state
            item["ao_vivo"] = True
            by_event[event_key] = item

    return list(by_event.values())


def betfair_live_payload():
    live = betfair_live_markets()
    items = []
    for m in live:
        start = m.get("start_time")
        dt = _flex_start_dt(start)
        elapsed = None
        if dt:
            elapsed = max(0, int((agora() - dt).total_seconds() // 60))

        items.append({
            "fixture_id": m.get("fixture_id"),
            "jogo": m.get("event_name") or "-",
            "casa": None,
            "fora": None,
            "liga": m.get("liga") or "Betfair",
            "pais": m.get("pais"),
            "horario": start,
            "start_time_iso": dt.isoformat() if dt else None,
            "ao_vivo": True,
            "status": "AO VIVO BETFAIR",
            "placar": m.get("placar"),
            "tempo_jogo": m.get("tempo_jogo") or (f"~{elapsed} min" if elapsed is not None else None),
            "market_id": m.get("market_id"),
            "event_id": m.get("event_id"),
            "market_name": m.get("market_name"),
            "live_source": m.get("live_source"),
            "dados_visiveis_frescos": betfair_visible_is_fresh(),
            "idade_dados_segundos": betfair_visible_age_seconds(),
            "total_matched": m.get("total_matched"),
            "favorite_selection": m.get("favorite_selection"),
            "favorite_odd": m.get("favorite_odd"),
            "favorite_amount": m.get("favorite_amount"),
            "back_book": m.get("back_book"),
            "lay_book": m.get("lay_book"),
            "linkado_marketid": bool(m.get("market_id") or m.get("linkado_marketid")),
            "linkado_matrix": bool(m.get("linkado_matrix")),
        })
    return items


def betfair_mirror_snapshot():
    with LOCK:
        markets = list(BETFAIR_MIRROR.get("markets") or [])
        meta = {
            "updated_at": BETFAIR_MIRROR.get("updated_at"),
            "filename": BETFAIR_MIRROR.get("filename"),
            "rows_received": BETFAIR_MIRROR.get("rows_received", 0),
            "error": BETFAIR_MIRROR.get("error"),
        }

    match_odds = [
        x for x in markets
        if _market_is_match_odds(x)
    ]
    linked = [x for x in markets if x.get("linkado_matrix")]
    with LOCK:
        visible_rows = list(BETFAIR_VISIBLE.get("rows") or [])
        visible_filename = BETFAIR_VISIBLE.get("filename")
        visible_updated_at = BETFAIR_VISIBLE.get("updated_at")
        visible_error = BETFAIR_VISIBLE.get("error")
    live = betfair_live_markets(visible_rows if visible_rows else markets)
    return {
        **meta,
        "markets": markets,
        "total": len(markets),
        "match_odds": len(match_odds),
        "linkados_sportmonks": len(linked),
        "ao_vivo_identificados": len(live),
        "dados_visiveis": len(visible_rows),
        "match_odds_visiveis": len([x for x in visible_rows if _market_is_match_odds(x)]),
        "visible_filename": visible_filename,
        "visible_updated_at": visible_updated_at,
        "visible_error": visible_error,
        "visible_age_seconds": betfair_visible_age_seconds(),
        "visible_fresh": betfair_visible_is_fresh(),
        "live_max_minutes": CONFIG["betfair_live_max_minutes"],
        "fresh_seconds": CONFIG["betfair_visible_fresh_seconds"],
        "fonte": "CSV EXPORTADO DO BF BOT MANAGER",
        "automatico": False,
        "observacao": "O BF Bot Manager não possui auto-exportação pública de mercados; esta lista espelha o último CSV exportado/importado.",
    }



app = FastAPI(title="MATRIX - FUTEBOL")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# Restaura os dois arquivos Betfair disponíveis no container.
_load_betfair_markets_cache()
_load_betfair_visible_cache()


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
    CSV principal: usa o nome real da seleção da Betfair sempre que possível.
    Para empate, usa "The Draw", que é o nome da seleção no Match Odds.
    SportMonksFixtureId continua no CSV como fallback.
    """
    code = str(signal.get("codigo_selecao") or "").upper()
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



def _bfbot_event_name(signal):
    """
    Bf Bot Manager/Betfair usa normalmente 'Time Casa v Time Fora'.
    """
    home = str(signal.get("casa") or "").strip()
    away = str(signal.get("fora") or "").strip()
    if home and away:
        return f"{home} v {away}"
    return str(signal.get("jogo") or "").replace(" x ", " v ").strip()


def _bfbot_start_time(signal):
    """
    Formato universal aceito pelo Bf Bot Manager:
    YYYY-MM-DD HH:MM:SS
    """
    raw = str(signal.get("start_time_iso") or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        dt_utc = dt.astimezone(ZoneInfo("UTC"))
        return dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _bfbot_sportmonks_selection(signal):
    code = str(signal.get("codigo_selecao") or "").upper()
    if code in ("HOME", "AWAY", "DRAW"):
        return code
    return str(signal.get("selecao") or "").strip()


def bfbot_tips():
    """
    Feed de EXECUÇÃO.
    Só envia tips aprovadas que tenham sido ligadas a um MarketId Betfair real
    vindo do CSV de mercados exportado do BF Bot Manager.

    Isso evita que o BF Bot Manager receba novas tips com Market ID = 0.
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
        if not s.get("selecao"):
            continue

        mins = _minutes_until_signal(s)
        if mins is not None and mins < CONFIG["bfbot_min_minutes_before_start"]:
            continue

        market = _find_betfair_market_for_signal(s)
        if not market:
            continue

        market_id = str(market.get("market_id") or "").strip()
        if not market_id:
            continue

        selection = _betfair_selection_name(s)
        if not selection:
            continue

        event_key = (market_id, _norm_text(selection))
        if event_key in seen:
            continue
        seen.add(event_key)

        row = {
            "Provider": CONFIG["bfbot_provider"],
            "MarketId": market_id,
            "SelectionName": selection,
            "EventName": str(market.get("event_name") or _bfbot_event_name(s)),
            "MarketType": "MATCH_ODDS",
            "BetType": "BACK",
            "Size": f"{float(s.get('stake_padrao') or CONFIG['stake']):.2f}",
            "BSP": "False",
        }

        event_id = str(market.get("event_id") or "").strip()
        if event_id:
            row["EventId"] = event_id

        rows.append(row)

        if len(rows) >= CONFIG["bfbot_max_tips"]:
            break

    return rows


def bfbot_unmatched_signals():
    """
    Sinais aprovados que ainda não possuem MarketId Betfair no espelho importado.
    Eles aparecem no painel, mas NÃO entram no feed de execução.
    """
    with LOCK:
        signals = list(STATE.get("sinais") or [])

    out = []
    for s in signals:
        if s.get("ao_vivo") or s.get("status") != "APROVADO":
            continue
        market = _find_betfair_market_for_signal(s)
        if market and market.get("market_id"):
            continue
        out.append({
            "fixture_id": s.get("fixture_id"),
            "jogo": s.get("jogo"),
            "selecao": s.get("selecao"),
            "horario": s.get("horario"),
            "motivo": "Aguardando MarketId no espelho Betfair/BF Bot Manager.",
        })
    return out



def bfbot_test_marketid_csv_text():
    """
    Diagnostic-only tip for confirming direct MarketId linking in BF Bot Manager.
    It is intentionally NOT included in the main MATRIX feed.
    Keep all betting strategies PAUSED while importing this file.
    """
    fields = [
        "Provider", "MarketId", "SelectionName", "EventName",
        "MarketType", "BetType", "Size", "BSP"
    ]
    row = {
        "Provider": "MATRIX_TESTE_NAO_APOSTAR",
        "MarketId": "1.261459879",
        "SelectionName": "Sabah FA",
        "EventName": "Sabah FA v Imigresen FC",
        "MarketType": "MATCH_ODDS",
        "BetType": "BACK",
        "Size": "0.01",
        "BSP": "False",
    }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    return buf.getvalue()


def bfbot_csv_text():
    rows = bfbot_tips()
    fields = [
        "Provider", "MarketId", "EventId", "SelectionName",
        "EventName", "MarketType", "BetType", "Size", "BSP"
    ]
    normalized_rows = []
    for row in rows:
        normalized_rows.append({k: row.get(k, "") for k in fields})

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(normalized_rows)
    return buf.getvalue()




def bfbot_tips_sportmonks():
    """
    Feed secundário usando o formato SportMonks puro documentado pelo Bf Bot Manager.
    Não é o feed principal. Serve como fallback perto do início da partida.
    """
    if not CONFIG["bfbot_enabled"]:
        return []

    with LOCK:
        signals = list(STATE.get("sinais") or [])

    rows = []
    seen = set()
    for s in signals:
        if s.get("ao_vivo") or s.get("status") != "APROVADO":
            continue
        if not s.get("fixture_id"):
            continue

        key = (s.get("fixture_id"), s.get("codigo_selecao"))
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "SportMonksFixtureId": str(s.get("fixture_id") or ""),
            "Provider": CONFIG["bfbot_provider"],
            "SelectionName": _bfbot_sportmonks_selection(s),
            "MarketType": "MATCH_ODDS",
            "Size": f"{float(s.get('stake_padrao') or CONFIG['stake']):.2f}",
            "Price": "0",
            "BetType": "BACK",
            "BSP": "False",
        })
        if len(rows) >= CONFIG["bfbot_max_tips"]:
            break
    return rows


def bfbot_csv_sportmonks_text():
    fields = [
        "SportMonksFixtureId", "Provider", "SelectionName",
        "MarketType", "Size", "Price", "BetType", "BSP"
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(bfbot_tips_sportmonks())
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
        "versao": "V3.12 AO VIVO ATUALIZADO + BETFAIR + MARKETID",
        "config": CONFIG,
        "conta": account_info(),
        "betfair_mirror": betfair_mirror_snapshot(),
        "betfair_ao_vivo": betfair_live_payload(),
        "bfbot": {
            "habilitado": CONFIG["bfbot_enabled"],
            "provider": CONFIG["bfbot_provider"],
            "tips_prontas": len(tips),
            "market_type": "MATCH_ODDS",
            "bet_type": "BACK",
            "minutos_antes": CONFIG["bfbot_min_minutes_before_start"],
            "feed_path": "/bfbot/tips.csv",
        "test_marketid_path": "/bfbot/test_marketid.csv",
            "test_marketid_path": "/bfbot/test_marketid.csv",
            "sportmonks_fixture_id": True,
            "csv_direto": True,
            "start_time_utc": True,
            "event_name_betfair": True,
            "bsp": False,
            "modo": "FEED PARA BFBOT MANAGER",
        },
        **state_copy,
    })


@app.post("/api/analisar")
def analisar():
    run_analysis()
    return status()




@app.post("/api/betfair/markets/import")
async def import_betfair_markets(request: Request):
    try:
        payload = await request.json()
        text = str(payload.get("csv") or "")
        filename = str(payload.get("filename") or "markets.csv")
        if len(text) > 5_000_000:
            return JSONResponse({"ok": False, "erro": "CSV maior que 5 MB."}, status_code=413)

        markets = parse_betfair_markets_csv(text)
        _save_betfair_markets_cache(text)
        with LOCK:
            BETFAIR_MIRROR["markets"] = markets
            BETFAIR_MIRROR["updated_at"] = agora().isoformat()
            BETFAIR_MIRROR["filename"] = filename
            BETFAIR_MIRROR["rows_received"] = len(markets)
            BETFAIR_MIRROR["error"] = None
        return JSONResponse({"ok": True, **betfair_mirror_snapshot()})
    except Exception as e:
        with LOCK:
            BETFAIR_MIRROR["error"] = str(e)
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=400)




@app.post("/api/betfair/visible/import")
async def import_betfair_visible(request: Request):
    try:
        payload = await request.json()
        text = str(payload.get("csv") or "")
        filename = str(payload.get("filename") or "betfair_visiveis.csv")
        if len(text) > 8_000_000:
            return JSONResponse({"ok": False, "erro": "CSV maior que 8 MB."}, status_code=413)

        rows = parse_betfair_visible_csv(text)
        _save_betfair_visible_cache(text)

        with LOCK:
            BETFAIR_VISIBLE["rows"] = rows
            BETFAIR_VISIBLE["updated_at"] = agora().isoformat()
            BETFAIR_VISIBLE["filename"] = filename
            BETFAIR_VISIBLE["rows_received"] = len(rows)
            BETFAIR_VISIBLE["error"] = None

        live = betfair_live_markets(rows)
        return JSONResponse({
            "ok": True,
            "total": len(rows),
            "match_odds": len([x for x in rows if _market_is_match_odds(x)]),
            "ao_vivo_identificados": len(live),
            "com_marketid": len([x for x in rows if x.get("market_id")]),
            "filename": filename,
        })
    except Exception as e:
        with LOCK:
            BETFAIR_VISIBLE["error"] = str(e)
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=400)


@app.get("/api/betfair/visible")
def get_betfair_visible():
    with LOCK:
        rows = list(BETFAIR_VISIBLE.get("rows") or [])
    return JSONResponse({
        "total": len(rows),
        "match_odds": len([x for x in rows if _market_is_match_odds(x)]),
        "ao_vivo_identificados": len(betfair_live_markets(rows)),
        "com_marketid": len([x for x in rows if x.get("market_id")]),
        "rows": rows,
    })


@app.get("/api/betfair/live")
def get_betfair_live():
    rows = betfair_live_payload()
    return JSONResponse({
        "total": len(rows),
        "jogos": rows,
        "fonte": "BETFAIR/BF BOT MANAGER",
        "observacao": "CONFIRMADO quando há InPlay; caso contrário, pode ser inferido pelo horário do mercado exportado."
    })


@app.get("/api/betfair/markets")
def get_betfair_markets():
    return JSONResponse(betfair_mirror_snapshot())


@app.get("/api/account")
def api_account():
    return JSONResponse(account_info())




@app.get("/bfbot/test_marketid.csv", response_class=PlainTextResponse)
def bfbot_test_marketid_feed():
    return PlainTextResponse(
        bfbot_test_marketid_csv_text(),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )



@app.get("/api/bfbot/unmatched")
def bfbot_unmatched():
    rows = bfbot_unmatched_signals()
    return JSONResponse({
        "total": len(rows),
        "sinais": rows,
        "mensagem": "Estes sinais não entram no feed de execução até existir MarketId Betfair correspondente."
    })


@app.get("/bfbot/tips.csv", response_class=PlainTextResponse)
def bfbot_feed():
    return PlainTextResponse(
        bfbot_csv_text(),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )



@app.get("/bfbot/tips_sportmonks.csv", response_class=PlainTextResponse)
def bfbot_feed_sportmonks():
    return PlainTextResponse(
        bfbot_csv_sportmonks_text(),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/bfbot")
def bfbot_status():
    tips = bfbot_tips()
    unmatched = bfbot_unmatched_signals()
    mirror = betfair_mirror_snapshot()
    return JSONResponse({
        "habilitado": CONFIG["bfbot_enabled"],
        "provider": CONFIG["bfbot_provider"],
        "tips_prontas": len(tips),
        "tips_com_marketid": len(tips),
        "sinais_sem_marketid": len(unmatched),
        "mercados_betfair_importados": mirror.get("total", 0),
        "feed_path": "/bfbot/tips.csv",
        "test_marketid_path": "/bfbot/test_marketid.csv",
        "marketid_obrigatorio": True,
        "bsp": False,
        "market_type": "MATCH_ODDS",
        "bet_type": "BACK",
        "minutos_antes": CONFIG["bfbot_min_minutes_before_start"],
        "tips": tips,
        "sem_marketid": unmatched,
    })


@app.get("/health")
def health():
    return {"ok": True, "versao": "3.12"}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))
