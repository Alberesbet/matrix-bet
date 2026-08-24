import os, time, threading, statistics, csv, io, re, unicodedata, math, json
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
    "forma_recente_jogos": int(os.getenv("MATRIX_FORMA_RECENTE_JOGOS", "2")),
    "forma_recente_dias": int(os.getenv("MATRIX_FORMA_RECENTE_DIAS", "90")),
    "forma_recente_peso_max": float(os.getenv("MATRIX_FORMA_RECENTE_PESO", "0.20")),
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

    # AUTO DEMO: somente simulação local no painel.
    "demo_auto_enabled": os.getenv("MATRIX_DEMO_AUTO", "true").strip().lower() in ("1","true","yes","sim"),
    "demo_bank": float(os.getenv("MATRIX_DEMO_BANK", "1000")),
    "demo_stake": float(os.getenv("MATRIX_DEMO_STAKE", "10")),
    "demo_odd_min": float(os.getenv("MATRIX_DEMO_ODD_MIN", "1.30")),
    "demo_odd_max": float(os.getenv("MATRIX_DEMO_ODD_MAX", "3.50")),
    "demo_min_market_liquidity": float(os.getenv("MATRIX_DEMO_MIN_MARKET_LIQUIDITY", "500")),
    "demo_min_selection_value": float(os.getenv("MATRIX_DEMO_MIN_SELECTION_VALUE", "50")),
    "demo_min_live_minute": int(os.getenv("MATRIX_DEMO_MIN_LIVE_MINUTE", "2")),
    "demo_max_live_minute": int(os.getenv("MATRIX_DEMO_MAX_LIVE_MINUTE", "75")),
    "demo_max_per_event": int(os.getenv("MATRIX_DEMO_MAX_PER_EVENT", "3")),
    "demo_max_open": int(os.getenv("MATRIX_DEMO_MAX_OPEN", "20")),
    "demo_data_max_age_seconds": int(os.getenv("MATRIX_DEMO_DATA_MAX_AGE_SECONDS", "900")),

    # Betfair API opcional para volume CORRESPONDIDO por seleção/time.
    # Nunca exponha essas chaves no navegador; configure somente como Environment Variables no servidor.
    "betfair_app_key": os.getenv("BETFAIR_APP_KEY", "").strip(),
    "betfair_session_token": os.getenv("BETFAIR_SESSION_TOKEN", "").strip(),
    "betfair_api_url": os.getenv(
        "BETFAIR_API_URL",
        "https://api.betfair.com/exchange/betting/json-rpc/v1"
    ).strip(),
    "betfair_runner_volume_ttl": int(os.getenv("BETFAIR_RUNNER_VOLUME_TTL", "15")),
    "betfair_catalog_sync_seconds": int(os.getenv("BETFAIR_CATALOG_SYNC_SECONDS", "300")),
    "betfair_catalog_days": int(os.getenv("BETFAIR_CATALOG_DAYS", "7")),
    "demo_server_engine": os.getenv("MATRIX_DEMO_SERVER_ENGINE", "true").strip().lower() in ("1","true","yes","sim"),
    "demo_server_tick_seconds": int(os.getenv("MATRIX_DEMO_SERVER_TICK_SECONDS", "12")),
    "demo_finish_grace_minutes": int(os.getenv("MATRIX_DEMO_FINISH_GRACE_MINUTES", "130")),
    "sportmonks_reconcile_ttl": int(os.getenv("MATRIX_RECONCILE_TTL", "45")),
    "sportmonks_reconcile_days_back": int(os.getenv("MATRIX_RECONCILE_DAYS_BACK", "2")),
    "live_status_max_age_seconds": int(os.getenv("MATRIX_LIVE_STATUS_MAX_AGE", "75")),

    # Histórico DEMO compartilhado entre notebook/celular.
    # O arquivo é um cache de servidor. Os navegadores também reidratam a nuvem
    # automaticamente, então os aparelhos convergem mesmo após reinício do serviço.
    "demo_cloud_file": os.getenv(
        "MATRIX_DEMO_CLOUD_FILE",
        "/tmp/matrix_demo_bets_cloud.json"
    ).strip(),

    # Mantido FALSE durante o teste DEMO: mostra a confirmação por volume sem bloquear entradas.
    "demo_require_top_runner_volume": os.getenv(
        "MATRIX_DEMO_REQUIRE_TOP_RUNNER_VOLUME", "false"
    ).strip().lower() in ("1","true","yes","sim"),
}

STATE = {
    "status": "iniciando",
    "ultima_atualizacao": None,
    "jogos_encontrados": 0,
    "jogos_com_odds": 0,
    "jogos_analisados": 0,
    "libertadores": [],
    "internacionais": [],
    "brasileiros": [],
    "ao_vivo": [],
    "sinais": [],
    "todos": [],
    "erro": None,
}


# ============================================================
# DEMO CLOUD
# Histórico compartilhado entre todos os aparelhos que acessam
# este mesmo serviço MATRIX.
# ============================================================
DEMO_CLOUD_LOCK = threading.RLock()
DEMO_CLOUD_BETS = []
DEMO_CLOUD_UPDATED_AT = None


def _demo_cloud_path():
    return Path(CONFIG["demo_cloud_file"])


def _demo_bet_key(bet):
    if not isinstance(bet, dict):
        return None

    demo_key = str(bet.get("demo_key") or "").strip()
    if demo_key:
        return "demo:" + demo_key

    market_id = str(bet.get("market_id") or "").strip()
    selection = str(bet.get("selecao") or "").strip()
    market_kind = str(bet.get("market_kind") or bet.get("mercado") or "").strip()
    if market_id and selection:
        return "market:" + market_id + "|" + _norm_text(selection) + "|" + _norm_text(market_kind)

    bet_id = str(bet.get("id") or "").strip()
    if bet_id:
        return "id:" + bet_id

    return None


def _demo_status_rank(status):
    s = str(status or "AGUARDANDO RESULTADO").strip().upper()
    return {
        "AGUARDANDO RESULTADO": 1,
        "ANULADA": 3,
        "CANCELADA": 4,
        "GANHOU": 5,
        "PERDEU": 5,
    }.get(s, 2)


def _demo_merge_one(old, new):
    old = dict(old or {})
    new = dict(new or {})

    old_rank = _demo_status_rank(old.get("status"))
    new_rank = _demo_status_rank(new.get("status"))

    # Resultado liquidado vence versões pendentes/canceladas antigas.
    if new_rank > old_rank:
        primary, secondary = new, old
    elif old_rank > new_rank:
        primary, secondary = old, new
    else:
        # No mesmo status, conserva o registro mais completo.
        if len(new) >= len(old):
            primary, secondary = new, old
        else:
            primary, secondary = old, new

    merged = dict(secondary)
    merged.update({k: v for k, v in primary.items() if v is not None and v != ""})

    # Nunca perde informações úteis presentes apenas no outro aparelho.
    for k, v in secondary.items():
        if (k not in merged or merged.get(k) in (None, "")) and v not in (None, ""):
            merged[k] = v

    return merged


def _demo_cloud_merge(incoming):
    global DEMO_CLOUD_BETS, DEMO_CLOUD_UPDATED_AT

    clean = []
    for b in (incoming or []):
        if isinstance(b, dict) and _demo_bet_key(b):
            clean.append(dict(b))

    # Limite defensivo; é mais que suficiente para meses de teste.
    clean = clean[:10000]

    with DEMO_CLOUD_LOCK:
        by_key = {}

        for b in DEMO_CLOUD_BETS:
            k = _demo_bet_key(b)
            if k:
                by_key[k] = dict(b)

        for b in clean:
            k = _demo_bet_key(b)
            if not k:
                continue
            if k in by_key:
                by_key[k] = _demo_merge_one(by_key[k], b)
            else:
                by_key[k] = dict(b)

        merged = list(by_key.values())

        # Mais recentes primeiro quando houver timestamp/id.
        def sort_key(b):
            try:
                return int(b.get("id") or 0)
            except Exception:
                return 0

        merged.sort(key=sort_key, reverse=True)
        DEMO_CLOUD_BETS = merged
        DEMO_CLOUD_UPDATED_AT = agora().isoformat()

        _demo_cloud_save_locked()
        return [dict(x) for x in DEMO_CLOUD_BETS]


def _demo_cloud_save_locked():
    try:
        p = _demo_cloud_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "updated_at": DEMO_CLOUD_UPDATED_AT,
                    "bets": DEMO_CLOUD_BETS,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(p)
    except Exception:
        # O sync continua funcionando em memória mesmo se o cache em disco falhar.
        pass


def _demo_cloud_load():
    global DEMO_CLOUD_BETS, DEMO_CLOUD_UPDATED_AT
    try:
        p = _demo_cloud_path()
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        bets = data.get("bets") if isinstance(data, dict) else []
        if not isinstance(bets, list):
            return

        with DEMO_CLOUD_LOCK:
            DEMO_CLOUD_BETS = [
                dict(b) for b in bets
                if isinstance(b, dict) and _demo_bet_key(b)
            ]
            DEMO_CLOUD_UPDATED_AT = (
                data.get("updated_at") if isinstance(data, dict) else None
            )
    except Exception:
        pass


def demo_cloud_snapshot():
    with DEMO_CLOUD_LOCK:
        bets = [dict(x) for x in DEMO_CLOUD_BETS]

    auto = [
        b for b in bets
        if b.get("auto_demo") is True or str(b.get("modo") or "") == "AUTO DEMO"
    ]
    pending_auto = [
        b for b in auto
        if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
    ]
    running_auto = [
        b for b in pending_auto
        if str(b.get("status_operacional") or "") == "EM ANDAMENTO"
    ]
    waiting_final_auto = [
        b for b in pending_auto
        if str(b.get("status_operacional") or "") == "AGUARDANDO CONFIRMAÇÃO FINAL"
    ]
    finished_auto = [
        b for b in auto
        if str(b.get("status") or "") in ("GANHOU", "PERDEU")
    ]
    canceled = [
        b for b in bets
        if str(b.get("status") or "") in ("CANCELADA", "ANULADA")
    ]
    wins = [b for b in bets if str(b.get("status") or "") == "GANHOU"]
    losses = [b for b in bets if str(b.get("status") or "") == "PERDEU"]

    running_events = {
        str(b.get("event_id") or b.get("fixture_id") or _norm_text(b.get("jogo")))
        for b in running_auto
        if str(b.get("event_id") or b.get("fixture_id") or _norm_text(b.get("jogo")))
    }

    effective_stake = sum(
        float(b.get("stake") or 0)
        for b in bets
        if str(b.get("status") or "") not in ("CANCELADA", "ANULADA")
    )
    canceled_stake = sum(float(b.get("stake") or 0) for b in canceled)
    open_stake = sum(float(b.get("stake") or 0) for b in pending_auto)
    settled_stake = sum(
        float(b.get("stake") or 0)
        for b in bets
        if str(b.get("status") or "") in ("GANHOU", "PERDEU")
    )
    movement = sum(float(b.get("stake") or 0) for b in bets)

    return {
        "ok": True,
        "bets": bets,
        "total": len(bets),
        "auto_demo_total": len(auto),
        "auto_demo_em_andamento": len(running_auto),
        "auto_demo_partidas_em_andamento": len(running_events),
        "auto_demo_aguardando_final": len(waiting_final_auto),
        "auto_demo_finalizadas": len(finished_auto),
        "vitorias": len(wins),
        "derrotas": len(losses),
        "canceladas": len(canceled),
        "pendentes": len(pending_auto),
        "valor_apostado_efetivo": round(effective_stake, 2),
        "valor_em_andamento": round(open_stake, 2),
        "valor_finalizado": round(settled_stake, 2),
        "valor_cancelado": round(canceled_stake, 2),
        "movimentacao_registrada": round(movement, 2),
        "updated_at": DEMO_CLOUD_UPDATED_AT,
        "sync": "SERVIDOR ÚNICO / CANÔNICO",
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

TEAM_FORM_CACHE = {}
TEAM_FORM_TTL = 2 * 60 * 60

BETFAIR_RUNNER_VOLUME_CACHE = {}
BETFAIR_RUNNER_VOLUME_LOCK = threading.RLock()

DEMO_SERVER_TICK_LOCK = threading.RLock()
DEMO_SERVER_LAST_TICK = 0.0
BETFAIR_CATALOG_LAST_SYNC = 0.0
BETFAIR_CATALOG_SYNC_LOCK = threading.RLock()
SPORTMONKS_SETTLE_CACHE = {}
SPORTMONKS_SETTLE_TTL = 60

SPORTMONKS_RECONCILE_LOCK = threading.RLock()
SPORTMONKS_RECONCILE_CACHE = {
    "ts": 0.0,
    "fixtures": [],
    "live_ids": set(),
    "live_names": set(),
    "error": None,
}



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
                "casa": matrix.get("casa"),
                "fora": matrix.get("fora"),
                "casa_id": matrix.get("casa_id"),
                "fora_id": matrix.get("fora_id"),
                "forma_recente": matrix.get("forma_recente"),
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
        winners = _row_get(raw, "Vencedor(es)", "Vencedores", "Winner(s)", "Winners")
        my_selections = _row_get(raw, "Minhas seleções", "Minhas selecoes", "My selections")
        lp = _row_get(raw, "L/P", "P/L", "Profit/Loss")
        bets_text = _row_get(raw, "Apostas", "Bets")

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
            "winners": winners or None,
            "my_selections": my_selections or None,
            "lp": lp or None,
            "bets_text": bets_text or None,
            "market_id": (mirror or {}).get("market_id"),
            "event_id": (mirror or {}).get("event_id"),
            "linkado_marketid": bool((mirror or {}).get("market_id")),
            "linkado_matrix": bool(matrix),
        }

        if matrix:
            item.update({
                "fixture_id": matrix.get("fixture_id"),
                "casa": matrix.get("casa"),
                "fora": matrix.get("fora"),
                "casa_id": matrix.get("casa_id"),
                "fora_id": matrix.get("fora_id"),
                "forma_recente": matrix.get("forma_recente"),
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



def _find_betfair_visible_for_signal(signal):
    """
    Localiza o mesmo jogo no CSV 'Exportar todos os dados visíveis'.
    Usado somente para obter a odd da BETFAIR.
    """
    sh, sa = _signal_event_names(signal)
    if not sh or not sa:
        return None

    with LOCK:
        rows = list(BETFAIR_VISIBLE.get("rows") or [])

    candidates = []
    for row in rows:
        if not _market_is_match_odds(row):
            continue

        mh, ma = _market_event_names(row)
        exact = (sh == mh and sa == ma)
        reverse = (sh == ma and sa == mh)
        fuzzy = False
        if mh and ma:
            fuzzy = ((sh in mh or mh in sh) and (sa in ma or ma in sa))

        if not (exact or reverse or fuzzy):
            continue

        score = 100 if exact else (80 if reverse else 60)

        signal_dt = _flex_start_dt(signal.get("start_time_iso"))
        row_dt = _flex_start_dt(row.get("start_time"))
        delta = None
        if signal_dt and row_dt:
            delta = abs((signal_dt - row_dt).total_seconds())
            if delta <= 15 * 60:
                score += 30
            elif delta <= 60 * 60:
                score += 10
            elif delta > 6 * 60 * 60:
                score -= 40

        candidates.append((score, delta if delta is not None else 10**12, row))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    if candidates[0][0] < 60:
        return None
    return candidates[0][2]


def _betfair_odd_for_signal(signal):
    """
    A MATRIX nunca cria uma odd para executar aposta.
    Retorna somente a odd BETFAIR observada no CSV de dados visíveis.

    O CSV recebido expõe diretamente a odd do 1º favorito.
    Portanto essa odd só é aceita quando o favorito é a mesma seleção
    escolhida pela análise MATRIX.
    """
    row = _find_betfair_visible_for_signal(signal)
    selection = str(_betfair_selection_name(signal) or "").strip()

    if not row:
        return {
            "ok": False,
            "odd": None,
            "fonte": "BETFAIR",
            "fresca": False,
            "motivo": "Jogo não encontrado nos dados visíveis da Betfair.",
        }

    fav = str(row.get("favorite_selection") or "").strip()
    odd = row.get("favorite_odd")
    fresh = betfair_visible_is_fresh()

    if not selection or not fav or _norm_text(selection) != _norm_text(fav):
        return {
            "ok": False,
            "odd": None,
            "fonte": "BETFAIR",
            "fresca": fresh,
            "favorite_selection": fav or None,
            "favorite_odd": odd,
            "motivo": f"A odd disponível no CSV é do favorito {fav or '-'}, não da seleção {selection or '-'}.",
        }

    if odd is None:
        return {
            "ok": False,
            "odd": None,
            "fonte": "BETFAIR",
            "fresca": fresh,
            "favorite_selection": fav or None,
            "motivo": "Odd Betfair não disponível.",
        }

    if not fresh:
        return {
            "ok": False,
            "odd": float(odd),
            "fonte": "BETFAIR",
            "fresca": False,
            "favorite_selection": fav or None,
            "motivo": "Odd Betfair importada está desatualizada.",
        }

    return {
        "ok": True,
        "odd": float(odd),
        "fonte": "BETFAIR",
        "fresca": True,
        "favorite_selection": fav or None,
        "motivo": "Odd Betfair atual importada do BF Bot Manager.",
    }


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



def betfair_api_live_snapshot():
    if not _betfair_api_ready():
        return []

    with LOCK:
        markets = [
            dict(x) for x in (BETFAIR_MIRROR.get("markets") or [])
            if str(x.get("market_id") or "") and _market_is_match_odds(x)
        ]

    ids = [str(x.get("market_id")) for x in markets[:200]]
    books = betfair_market_results(ids)
    by_id = {str(x.get("market_id")): x for x in markets}
    out = []

    for mid, book in books.items():
        if not book.get("ok") or not book.get("inplay"):
            continue

        m = by_id.get(mid) or {}
        dt = _flex_start_dt(m.get("start_time"))
        elapsed = max(0, int((agora() - dt).total_seconds() // 60)) if dt else None

        out.append({
            "fixture_id": m.get("fixture_id"),
            "jogo": m.get("event_name") or "-",
            "casa": m.get("casa"),
            "fora": m.get("fora"),
            "liga": m.get("competition") or m.get("liga") or "Betfair",
            "pais": m.get("country_code") or m.get("pais"),
            "horario": m.get("start_time"),
            "ao_vivo": True,
            "status": "AO VIVO CONFIRMADO",
            "tempo_jogo": f"~{elapsed} min" if elapsed is not None else None,
            "market_id": mid,
            "event_id": m.get("event_id"),
            "market_name": m.get("market_name"),
            "live_source": "BETFAIR_API_CONFIRMADO",
            "dados_visiveis_frescos": True,
            "total_matched": book.get("total_matched"),
            "linkado_marketid": True,
            "linkado_matrix": bool(m.get("linkado_matrix")),
        })

    return out


def betfair_live_payload():
    api_live = betfair_api_live_snapshot()
    if api_live:
        return api_live

    # Sem API Betfair, NÃO contamos mais "provável ao vivo" como ao vivo real.
    # Somente linhas explicitamente confirmadas como in-play entram aqui.
    live = [
        m for m in betfair_live_markets()
        if str(m.get("live_source") or "") == "CONFIRMADO"
    ]
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
            "status": "AO VIVO CONFIRMADO",
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



def _demo_market_kind(market):
    name = _norm_text(market.get("market_name"))
    if _market_is_match_odds(market):
        return "MATCH_ODDS"
    if (
        "mais menos de 1 5" in name
        or "over under 1 5" in name
        or "over under 1.5" in name
    ):
        return "OVER_UNDER_15"

    if (
        "mais menos de 2 5" in name
        or "over under 2 5" in name
        or "over under 2.5" in name
    ):
        return "OVER_UNDER_25"
    if (
        ("ambas" in name and "marcam" in name)
        or ("both teams" in name and "score" in name)
    ):
        return "BOTH_TEAMS_SCORE"
    return None


def _demo_elapsed_minutes(market):
    dt = _flex_start_dt(market.get("start_time"))
    if not dt:
        return None
    return max(0, int((agora() - dt).total_seconds() // 60))


def _demo_visible_fresh_enough():
    age = betfair_visible_age_seconds()
    return age is not None and age <= CONFIG["demo_data_max_age_seconds"]


def demo_live_candidates():
    """
    Entradas AUTOMÁTICAS DE DEMONSTRAÇÃO.
    Nunca envia uma ordem real à Betfair.

    O campo favorite_amount vem do texto do BF Bot Manager, por exemplo:
      Sabah FA, R$515,77@2,32
    Esse R$515,77 é tratado como VALOR DISPONÍVEL NA SELEÇÃO/preço exibido,
    e não como percentual de apostadores ou total já apostado no time.
    """
    if not CONFIG["demo_auto_enabled"]:
        return []

    with LOCK:
        rows = list(BETFAIR_VISIBLE.get("rows") or [])

    if not rows or not _demo_visible_fresh_enough():
        return []

    eligible = []
    for row in rows:
        live_state = _market_live_state(row)
        if not live_state:
            continue

        kind = _demo_market_kind(row)
        if not kind:
            continue

        market_id = str(row.get("market_id") or "").strip()
        selection = str(row.get("favorite_selection") or "").strip()
        odd = row.get("favorite_odd")
        selection_value = row.get("favorite_amount")
        market_liquidity = row.get("total_matched_num")
        elapsed = _demo_elapsed_minutes(row)

        if not market_id or not selection or odd is None or elapsed is None:
            continue

        try:
            odd = float(odd)
            selection_value = float(selection_value or 0)
            market_liquidity = float(market_liquidity or 0)
        except Exception:
            continue

        if odd < CONFIG["demo_odd_min"] or odd > CONFIG["demo_odd_max"]:
            continue
        if market_liquidity < CONFIG["demo_min_market_liquidity"]:
            continue
        if selection_value < CONFIG["demo_min_selection_value"]:
            continue
        if elapsed < CONFIG["demo_min_live_minute"] or elapsed > CONFIG["demo_max_live_minute"]:
            continue

        # Em Match Odds, não usa o empate como "time com valor".
        if kind == "MATCH_ODDS" and _norm_text(selection) in ("the draw", "draw", "empate"):
            continue

        implied = round(100.0 / odd, 1)

        forma_recente = row.get("forma_recente") or {}
        forma_selecao = None
        forma_confirmada = None
        forma_vantagem = forma_recente.get("vantagem")

        if forma_recente.get("disponivel"):
            if _norm_text(selection) == _norm_text(row.get("casa")):
                forma_selecao = (forma_recente.get("casa") or {})
            elif _norm_text(selection) == _norm_text(row.get("fora")):
                forma_selecao = (forma_recente.get("fora") or {})

            if forma_vantagem and forma_vantagem != "EQUILIBRADO":
                forma_confirmada = _norm_text(selection) == _norm_text(forma_vantagem)
            elif forma_vantagem == "EQUILIBRADO":
                forma_confirmada = True

        # Peso extra para seleção que possui maior valor visível no próprio nome/linha.
        # É um índice de triagem, não probabilidade real.
        selection_value_score = min(20.0, max(0.0, math.log10(max(selection_value, 1)) * 5.0))
        liquidity_score = min(15.0, max(0.0, math.log10(max(market_liquidity, 1)) * 3.0))
        form_bonus = 0.0
        if forma_selecao and forma_selecao.get("disponivel"):
            # No máximo +5 pontos no índice DEMO. Forma recente é confirmação,
            # não substitui odd/liquidez.
            form_bonus = min(5.0, float(forma_selecao.get("forca_pct") or 0) * 0.05)

        demo_score = round(
            min(99.0, implied * 0.70 + selection_value_score + liquidity_score + form_bonus),
            1
        )

        stake = float(CONFIG["demo_stake"])
        retorno = round(stake * odd, 2)
        lucro = round(retorno - stake, 2)

        eligible.append({
            "demo_key": f"{market_id}|{_norm_text(selection)}",
            "event_key": str(row.get("event_id") or _norm_text(row.get("event_name"))),
            "event_id": row.get("event_id"),
            "market_id": market_id,
            "fixture_id": row.get("fixture_id"),
            "casa": row.get("casa"),
            "fora": row.get("fora"),
            "liga": row.get("liga") or "Betfair",
            "jogo": row.get("event_name"),
            "mercado": row.get("market_name"),
            "market_kind": kind,
            "selecao": selection,
            "odd": odd,
            "stake": stake,
            "retorno_potencial": retorno,
            "lucro_potencial": lucro,
            "minuto": elapsed,
            "valor_na_selecao": selection_value,
            "valor_na_selecao_texto": (
                f"R$ {selection_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            ),
            "total_correspondido": row.get("total_matched"),
            "liquidez": market_liquidity,
            "prob_implicita": implied,
            "indice_demo": demo_score,
            "forma_recente": forma_recente,
            "forma_time_escolhido": forma_selecao,
            "forma_vantagem": forma_vantagem,
            "forma_confirma_entrada": forma_confirmada,
            "time_favorito_betfair": selection,
            "confirmacao_favorito": True,
            "valor_minimo_selecao": CONFIG["demo_min_selection_value"],
            "liquidez_minima_mercado": CONFIG["demo_min_market_liquidity"],
            "janela_minuto_min": CONFIG["demo_min_live_minute"],
            "janela_minuto_max": CONFIG["demo_max_live_minute"],
            "live_source": live_state,
            "start_time": row.get("start_time"),
            "fonte_odd": "BETFAIR",
            "modo": "AUTO DEMO",
            "motivo": (
                f"Entrada AUTO DEMO aprovada porque {selection} é o 1º favorito exibido "
                f"pelo BF Bot/Betfair; minuto ~{elapsed} dentro da janela "
                f"{CONFIG['demo_min_live_minute']}-{CONFIG['demo_max_live_minute']}; "
                f"odd Betfair {odd:.2f} dentro da faixa {CONFIG['demo_odd_min']:.2f}-"
                f"{CONFIG['demo_odd_max']:.2f}; valor disponível na seleção "
                f"{selection_value:.2f} >= {CONFIG['demo_min_selection_value']:.2f}; "
                f"total correspondido do mercado {row.get('total_matched') or '-'} "
                f">= mínimo configurado; "
                f"forma recente: {forma_vantagem or 'sem dados suficientes'}."
            ),
        })

    priority = {"MATCH_ODDS": 0, "OVER_UNDER_15": 1, "OVER_UNDER_25": 2, "BOTH_TEAMS_SCORE": 3}
    by_event = {}
    for c in eligible:
        by_event.setdefault(c["event_key"], []).append(c)

    selected = []
    for group in by_event.values():
        group.sort(key=lambda x: (
            priority.get(x["market_kind"], 99),
            -x["indice_demo"],
            -x["valor_na_selecao"],
            -x["liquidez"],
        ))
        selected.extend(group[:CONFIG["demo_max_per_event"]])

    selected.sort(key=lambda x: (-x["indice_demo"], -x["valor_na_selecao"], -x["liquidez"]))
    return selected[:CONFIG["demo_max_open"]]


def demo_result_rows():
    with LOCK:
        rows = list(BETFAIR_VISIBLE.get("rows") or [])
    out = []
    for row in rows:
        winners = str(row.get("winners") or "").strip()
        market_id = str(row.get("market_id") or "").strip()
        if not winners or not market_id:
            continue
        out.append({
            "market_id": market_id,
            "event_id": row.get("event_id"),
            "jogo": row.get("event_name"),
            "mercado": row.get("market_name"),
            "winners": winners,
            "status": row.get("status"),
        })
    return out



def _betfair_api_ready():
    return bool(CONFIG["betfair_app_key"] and CONFIG["betfair_session_token"])


def _betfair_api_rpc(method, params):
    if not _betfair_api_ready():
        raise RuntimeError("BETFAIR_APP_KEY / BETFAIR_SESSION_TOKEN não configurados.")

    payload = [{
        "jsonrpc": "2.0",
        "method": f"SportsAPING/v1.0/{method}",
        "params": params,
        "id": 1,
    }]
    headers = {
        "X-Application": CONFIG["betfair_app_key"],
        "X-Authentication": CONFIG["betfair_session_token"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = requests.post(
        CONFIG["betfair_api_url"],
        headers=headers,
        json=payload,
        timeout=12,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError("Resposta inesperada da Betfair API.")
    item = data[0]
    if item.get("error"):
        raise RuntimeError(str(item["error"]))
    return item.get("result") or []


def _runner_volume_cache_get(market_id):
    now_ts = time.time()
    with BETFAIR_RUNNER_VOLUME_LOCK:
        item = BETFAIR_RUNNER_VOLUME_CACHE.get(market_id)
        if not item:
            return None
        if now_ts - item["ts"] > CONFIG["betfair_runner_volume_ttl"]:
            return None
        return item["value"]


def _runner_volume_cache_set(market_id, value):
    with BETFAIR_RUNNER_VOLUME_LOCK:
        BETFAIR_RUNNER_VOLUME_CACHE[market_id] = {
            "ts": time.time(),
            "value": value,
        }



def _iso_utc(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def betfair_catalogue_auto_sync(force=False):
    """
    Futebol Betfair sem filtro de país.
    Quando a API estiver configurada, inclui mercados brasileiros,
    estaduais/regionais quando existirem na Exchange.
    """
    global BETFAIR_CATALOG_LAST_SYNC

    if not _betfair_api_ready():
        return {
            "ok": False,
            "ativo": False,
            "motivo": "BETFAIR_APP_KEY / BETFAIR_SESSION_TOKEN não configurados.",
        }

    now_ts = time.time()
    with BETFAIR_CATALOG_SYNC_LOCK:
        if (
            not force
            and BETFAIR_CATALOG_LAST_SYNC
            and now_ts - BETFAIR_CATALOG_LAST_SYNC < CONFIG["betfair_catalog_sync_seconds"]
        ):
            with LOCK:
                count = len(BETFAIR_MIRROR.get("markets") or [])
            return {"ok": True, "ativo": True, "mercados": count, "cache": True}

        start = agora() - timedelta(hours=4)
        end = agora() + timedelta(days=CONFIG["betfair_catalog_days"])

        try:
            result = _betfair_api_rpc(
                "listMarketCatalogue",
                {
                    "filter": {
                        "eventTypeIds": ["1"],
                        "marketTypeCodes": [
                            "MATCH_ODDS",
                            "OVER_UNDER_15",
                            "OVER_UNDER_25",
                            "BOTH_TEAMS_TO_SCORE",
                        ],
                        "marketStartTime": {
                            "from": _iso_utc(start),
                            "to": _iso_utc(end),
                        },
                    },
                    "marketProjection": [
                        "EVENT",
                        "COMPETITION",
                        "MARKET_START_TIME",
                        "RUNNER_DESCRIPTION",
                    ],
                    "sort": "FIRST_TO_START",
                    "maxResults": "1000",
                },
            )

            api_markets = []
            for m in result:
                event = m.get("event") or {}
                comp = m.get("competition") or {}
                runners = [{
                    "selection_id": str(rr.get("selectionId") or ""),
                    "selection": rr.get("runnerName"),
                    "handicap": rr.get("handicap"),
                } for rr in (m.get("runners") or [])]

                api_markets.append({
                    "event_name": event.get("name") or "-",
                    "event_id": str(event.get("id") or ""),
                    "market_name": m.get("marketName") or "Mercado Betfair",
                    "market_id": str(m.get("marketId") or ""),
                    "start_time": m.get("marketStartTime"),
                    "total_matched": m.get("totalMatched"),
                    "total_matched_num": float(m.get("totalMatched") or 0),
                    "status": "API_CATALOG",
                    "in_play": False,
                    "competition": comp.get("name"),
                    "competition_id": comp.get("id"),
                    "country_code": event.get("countryCode"),
                    "timezone": event.get("timezone"),
                    "venue": event.get("venue"),
                    "runners_catalog": runners,
                    "source": "BETFAIR_API",
                    "linkado_marketid": True,
                })

            with LOCK:
                current = list(BETFAIR_MIRROR.get("markets") or [])
                by_id = {
                    str(x.get("market_id") or ""): dict(x)
                    for x in current
                    if str(x.get("market_id") or "")
                }
                for x in api_markets:
                    mid = str(x.get("market_id") or "")
                    old = by_id.get(mid, {})
                    merged = dict(x)
                    # preserva campos enriquecidos do CSV, se existirem
                    for k, v in old.items():
                        if v not in (None, "", [], {}):
                            merged[k] = v
                    merged["market_id"] = mid
                    merged["event_id"] = x.get("event_id") or merged.get("event_id")
                    merged["source_catalog"] = "BETFAIR_API"
                    by_id[mid] = merged

                BETFAIR_MIRROR["markets"] = list(by_id.values())
                BETFAIR_MIRROR["updated_at"] = agora().isoformat()
                BETFAIR_MIRROR["filename"] = "BETFAIR_API + CSV"
                BETFAIR_MIRROR["rows_received"] = len(by_id)
                BETFAIR_MIRROR["error"] = None

            BETFAIR_CATALOG_LAST_SYNC = time.time()
            return {
                "ok": True,
                "ativo": True,
                "mercados_api": len(api_markets),
                "mercados_total": len(by_id),
                "janela_dias": CONFIG["betfair_catalog_days"],
                "sem_filtro_pais": True,
            }
        except Exception as e:
            with LOCK:
                BETFAIR_MIRROR["error"] = f"Betfair API catálogo: {e}"
            return {"ok": False, "ativo": True, "erro": str(e)}


def betfair_market_results(market_ids):
    """
    market.status CLOSED + runner.status WINNER/LOSER.
    É a fonte principal para encerrar apostas DEMO quando a API está conectada.
    """
    ids = [str(x).strip() for x in market_ids if str(x).strip()]
    ids = list(dict.fromkeys(ids))
    if not ids or not _betfair_api_ready():
        return {}

    out = {}
    for pos in range(0, len(ids), 20):
        batch = ids[pos:pos+20]
        try:
            catalogue = _betfair_api_rpc(
                "listMarketCatalogue",
                {
                    "filter": {"marketIds": batch},
                    "marketProjection": ["RUNNER_DESCRIPTION", "EVENT"],
                    "maxResults": str(len(batch)),
                },
            )
            names = {}
            for m in catalogue:
                mid = str(m.get("marketId") or "")
                names[mid] = {
                    str(r.get("selectionId")): r.get("runnerName")
                    for r in (m.get("runners") or [])
                }

            books = _betfair_api_rpc("listMarketBook", {"marketIds": batch})
            returned = set()

            for book in books:
                mid = str(book.get("marketId") or "")
                returned.add(mid)
                runners, winners = [], []
                for rr in (book.get("runners") or []):
                    sid = str(rr.get("selectionId") or "")
                    nm = names.get(mid, {}).get(sid) or sid
                    st = str(rr.get("status") or "").upper()
                    runners.append({
                        "selection_id": sid,
                        "selection": nm,
                        "status": st,
                        "total_matched": float(rr.get("totalMatched") or 0),
                    })
                    if st == "WINNER":
                        winners.append(nm)

                out[mid] = {
                    "ok": True,
                    "market_id": mid,
                    "status": str(book.get("status") or "").upper(),
                    "inplay": bool(book.get("inplay")),
                    "total_matched": float(book.get("totalMatched") or 0),
                    "winners": winners,
                    "runners": runners,
                    "source": "BETFAIR_API",
                }

            for mid in batch:
                if mid not in returned:
                    out[mid] = {
                        "ok": False,
                        "market_id": mid,
                        "source": "BETFAIR_API",
                        "reason": "Mercado não retornado.",
                    }
        except Exception as e:
            for mid in batch:
                out[mid] = {
                    "ok": False,
                    "market_id": mid,
                    "source": "BETFAIR_API",
                    "reason": str(e),
                }
    return out


def betfair_runner_volumes(market_ids):
    """
    Volume correspondido POR seleção/runner via API oficial Betfair.

    O CSV do BF Bot Manager fornece:
      - 1º favorito
      - valor disponível nessa cotação
      - total correspondido do MERCADO

    A API listMarketBook fornece runner.totalMatched e EX_TRADED,
    permitindo separar Hamburgo / Empate / Verl, por exemplo.
    """
    ids = [str(x).strip() for x in market_ids if str(x).strip()]
    ids = list(dict.fromkeys(ids))
    result = {}

    # Cache first.
    missing = []
    for mid in ids:
        cached = _runner_volume_cache_get(mid)
        if cached is not None:
            result[mid] = cached
        else:
            missing.append(mid)

    if not missing:
        return result

    if not _betfair_api_ready():
        for mid in missing:
            result[mid] = {
                "ok": False,
                "source": "BETFAIR_API",
                "reason": "API Betfair ainda não conectada no servidor.",
                "runners": [],
            }
        return result

    # EX_BEST_OFFERS + EX_TRADED has request weight; use max 10 markets per batch.
    for pos in range(0, len(missing), 10):
        batch = missing[pos:pos+10]
        try:
            catalog = _betfair_api_rpc(
                "listMarketCatalogue",
                {
                    "filter": {"marketIds": batch},
                    "maxResults": str(len(batch)),
                    "marketProjection": ["RUNNER_DESCRIPTION", "EVENT"],
                },
            )
            names = {}
            for m in catalog:
                mid = str(m.get("marketId") or "")
                names[mid] = {
                    str(r.get("selectionId")): r.get("runnerName")
                    for r in (m.get("runners") or [])
                }

            books = _betfair_api_rpc(
                "listMarketBook",
                {
                    "marketIds": batch,
                    "priceProjection": {
                        "priceData": ["EX_BEST_OFFERS", "EX_TRADED"],
                        "virtualise": True,
                    },
                },
            )

            returned = set()
            for book in books:
                mid = str(book.get("marketId") or "")
                returned.add(mid)
                runner_rows = []
                for rr in (book.get("runners") or []):
                    sid = str(rr.get("selectionId"))
                    ex = rr.get("ex") or {}
                    backs = ex.get("availableToBack") or []
                    lays = ex.get("availableToLay") or []
                    traded = ex.get("tradedVolume") or []
                    runner_rows.append({
                        "selection_id": sid,
                        "selection": names.get(mid, {}).get(sid) or sid,
                        "status": str(rr.get("status") or "").upper(),
                        "total_matched": float(rr.get("totalMatched") or 0),
                        "last_price_traded": rr.get("lastPriceTraded"),
                        "best_back_price": (backs[0].get("price") if backs else None),
                        "best_back_size": (backs[0].get("size") if backs else None),
                        "best_lay_price": (lays[0].get("price") if lays else None),
                        "best_lay_size": (lays[0].get("size") if lays else None),
                        "traded_volume": traded,
                    })

                runner_rows.sort(key=lambda x: x["total_matched"], reverse=True)
                value = {
                    "ok": True,
                    "source": "BETFAIR_API",
                    "market_id": mid,
                    "market_total_matched": float(book.get("totalMatched") or 0),
                    "market_status": str(book.get("status") or "").upper(),
                    "inplay": bool(book.get("inplay")),
                    "runners": runner_rows,
                    "top_runner": (runner_rows[0] if runner_rows else None),
                }
                result[mid] = value
                _runner_volume_cache_set(mid, value)

            for mid in batch:
                if mid not in returned:
                    value = {
                        "ok": False,
                        "source": "BETFAIR_API",
                        "reason": "MarketId não retornado pela Betfair API.",
                        "runners": [],
                    }
                    result[mid] = value
                    _runner_volume_cache_set(mid, value)

        except Exception as e:
            for mid in batch:
                value = {
                    "ok": False,
                    "source": "BETFAIR_API",
                    "reason": str(e),
                    "runners": [],
                }
                result[mid] = value
                _runner_volume_cache_set(mid, value)

    return result


def enrich_demo_candidates_with_runner_volume(candidates):
    if not candidates:
        return candidates

    volume_map = betfair_runner_volumes(
        [x.get("market_id") for x in candidates if x.get("market_id")]
    )

    for c in candidates:
        info = volume_map.get(str(c.get("market_id") or "")) or {}
        c["volume_por_selecao_disponivel"] = bool(info.get("ok"))
        c["volume_por_selecao_fonte"] = info.get("source") or "BETFAIR_API"
        c["volume_por_selecao_motivo"] = info.get("reason")
        c["volumes_selecoes"] = info.get("runners") or []

        top = info.get("top_runner") or {}
        c["selecao_maior_volume"] = top.get("selection")
        c["selecao_maior_volume_valor"] = top.get("total_matched")

        chosen = _norm_text(c.get("selecao"))
        top_name = _norm_text(top.get("selection"))
        c["confirmacao_maior_volume"] = bool(
            chosen and top_name and chosen == top_name
        )

    return candidates




def _fixture_pair(f):
    home, away = participants(f)
    return _norm_text(home.get("name")), _norm_text(away.get("name"))


def _bet_pair(bet):
    home = _norm_text(bet.get("casa"))
    away = _norm_text(bet.get("fora"))
    if home and away:
        return home, away
    return _event_pair(bet.get("jogo"))


def _team_name_close(a, b):
    a = _norm_text(a)
    b = _norm_text(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True

    # Remove common club prefixes/suffixes for a conservative fallback.
    stop = {
        "fc", "fk", "if", "sc", "cf", "afc", "ac", "club", "clube",
        "football", "futebol", "de", "da", "do", "the"
    }
    ta = [x for x in a.split() if x not in stop]
    tb = [x for x in b.split() if x not in stop]
    if not ta or not tb:
        return False

    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    return inter >= max(1, min(len(sa), len(sb)) - 1)


def _sportmonks_reconcile_pool(force=False):
    """
    Uma única consulta compartilhada serve para TODAS as apostas pendentes.
    Inclui partidas recentes/finalizadas e a lista in-play atual.
    """
    now_ts = time.time()

    with SPORTMONKS_RECONCILE_LOCK:
        age = now_ts - float(SPORTMONKS_RECONCILE_CACHE.get("ts") or 0)
        if (
            not force
            and SPORTMONKS_RECONCILE_CACHE.get("fixtures")
            and age <= CONFIG["sportmonks_reconcile_ttl"]
        ):
            return {
                "fixtures": list(SPORTMONKS_RECONCILE_CACHE["fixtures"]),
                "live_ids": set(SPORTMONKS_RECONCILE_CACHE["live_ids"]),
                "live_names": set(SPORTMONKS_RECONCILE_CACHE["live_names"]),
                "error": SPORTMONKS_RECONCILE_CACHE.get("error"),
                "age": age,
            }

    start = (agora() - timedelta(days=CONFIG["sportmonks_reconcile_days_back"])).date()
    end = (agora() + timedelta(days=1)).date()

    fixtures = []
    live_rows = []
    err = None

    try:
        fixtures = get_pages(
            f"/fixtures/between/{start.isoformat()}/{end.isoformat()}",
            {"include": "participants;league.country;state;scores"},
            max_pages=20,
        )
    except Exception as e:
        err = f"fixtures: {e}"

    try:
        live_rows = live_games()
    except Exception as e:
        if err:
            err += f" | livescores: {e}"
        else:
            err = f"livescores: {e}"

    live_ids = {
        str(f.get("id"))
        for f in live_rows
        if f.get("id") is not None
    }
    live_names = set()
    for f in live_rows:
        h, a = _fixture_pair(f)
        if h and a:
            live_names.add((h, a))
            live_names.add((a, h))

    with SPORTMONKS_RECONCILE_LOCK:
        SPORTMONKS_RECONCILE_CACHE["ts"] = time.time()
        SPORTMONKS_RECONCILE_CACHE["fixtures"] = list(fixtures)
        SPORTMONKS_RECONCILE_CACHE["live_ids"] = set(live_ids)
        SPORTMONKS_RECONCILE_CACHE["live_names"] = set(live_names)
        SPORTMONKS_RECONCILE_CACHE["error"] = err

    return {
        "fixtures": fixtures,
        "live_ids": live_ids,
        "live_names": live_names,
        "error": err,
        "age": 0,
    }


def _match_bet_to_fixture(bet, pool):
    """
    Liga apostas antigas ao SportMonks mesmo quando o Fixture ID não foi salvo.
    Critérios:
      1. Fixture ID já existente;
      2. nomes Casa/Fora;
      3. horário próximo como desempate.
    """
    fixtures = pool.get("fixtures") or []
    fid = str(bet.get("fixture_id") or "").strip()

    if fid:
        for f in fixtures:
            if str(f.get("id")) == fid:
                return f

    bh, ba = _bet_pair(bet)
    if not bh or not ba:
        return None

    bet_dt = _flex_start_dt(bet.get("horario") or bet.get("start_time"))
    candidates = []

    for f in fixtures:
        fh, fa = _fixture_pair(f)
        if not fh or not fa:
            continue

        exact = (bh == fh and ba == fa)
        reverse = (bh == fa and ba == fh)
        fuzzy = (
            _team_name_close(bh, fh) and _team_name_close(ba, fa)
        ) or (
            _team_name_close(bh, fa) and _team_name_close(ba, fh)
        )

        if not (exact or reverse or fuzzy):
            continue

        score = 100 if exact else (85 if reverse else 65)
        fixture_dt = parse_dt(f.get("starting_at"))
        delta = 10**12

        if bet_dt and fixture_dt:
            delta = abs((bet_dt - fixture_dt).total_seconds())
            if delta <= 15 * 60:
                score += 35
            elif delta <= 60 * 60:
                score += 20
            elif delta <= 3 * 60 * 60:
                score += 5
            else:
                score -= 35

        candidates.append((score, delta, f))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    if candidates[0][0] < 60:
        return None
    return candidates[0][2]


def _fixture_is_live_now(f, pool):
    if not f:
        return False

    fid = str(f.get("id") or "")
    if fid and fid in (pool.get("live_ids") or set()):
        return True

    h, a = _fixture_pair(f)
    if (h, a) in (pool.get("live_names") or set()):
        return True

    return False


def _fixture_final_payload(f):
    if not f:
        return None

    home, away = participants(f)
    scores = h2h_score_by_team(f)
    return {
        "fixture_id": str(f.get("id") or ""),
        "finished": _fixture_finished_state(f),
        "home": home.get("name"),
        "away": away.get("name"),
        "home_goals": scores.get(home.get("id")),
        "away_goals": scores.get(away.get("id")),
        "state": state_text(f),
        "source": "SPORTMONKS_RECONCILE",
    }


def _fixture_finished_state(f):
    st = f.get("state") or {}
    raw = " ".join([
        str(st.get("short_name") or ""),
        str(st.get("name") or ""),
        str(st.get("state") or ""),
        str(st.get("developer_name") or ""),
    ])
    n = _norm_text(raw)
    terms = (
        "ft", "finished", "full time", "after extra time",
        "aet", "after penalties", "pen", "ended", "finalizado"
    )
    return any(t == n or t in n for t in terms)


def _sportmonks_fixture_final(fixture_id):
    fid = str(fixture_id or "").strip()
    if not fid:
        return None

    cached = SPORTMONKS_SETTLE_CACHE.get(fid)
    if cached and time.time() - cached["ts"] < SPORTMONKS_SETTLE_TTL:
        return cached["data"]

    try:
        payload = api_get(
            f"/fixtures/{fid}",
            {"include": "participants;scores;state"},
        )
        f = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(f, dict):
            return None

        home, away = participants(f)
        scores = h2h_score_by_team(f)
        data = {
            "fixture_id": fid,
            "finished": _fixture_finished_state(f),
            "home": home.get("name"),
            "away": away.get("name"),
            "home_goals": scores.get(home.get("id")),
            "away_goals": scores.get(away.get("id")),
            "state": state_text(f),
            "source": "SPORTMONKS",
        }
        SPORTMONKS_SETTLE_CACHE[fid] = {"ts": time.time(), "data": data}
        return data
    except Exception:
        return None


def _selection_won_from_score(bet, final):
    if not final or not final.get("finished"):
        return None

    hg, ag = final.get("home_goals"), final.get("away_goals")
    if hg is None or ag is None:
        return None

    kind = str(bet.get("market_kind") or "").upper()
    selection = _norm_text(bet.get("selecao"))
    home = _norm_text(final.get("home"))
    away = _norm_text(final.get("away"))

    if kind == "MATCH_ODDS":
        winner = home if hg > ag else (away if ag > hg else "empate")
        return (
            selection == winner
            or selection in winner
            or winner in selection
            or (winner == "empate" and selection in ("draw", "the draw", "empate"))
        )

    total = int(hg) + int(ag)

    if kind == "OVER_UNDER_15":
        over = total >= 2
        if "mais" in selection or "over" in selection:
            return over
        if "menos" in selection or "under" in selection:
            return not over

    if kind == "OVER_UNDER_25":
        over = total >= 3
        if "mais" in selection or "over" in selection:
            return over
        if "menos" in selection or "under" in selection:
            return not over

    if kind == "BOTH_TEAMS_SCORE":
        yes = hg > 0 and ag > 0
        if selection in ("sim", "yes"):
            return yes
        if selection in ("nao", "no"):
            return not yes

    return None


def _settle_bet_object(b, won, source, result_text=None):
    stake = float(b.get("stake") or 0)
    odd = float(b.get("odd") or 0)

    b["status"] = "GANHOU" if won else "PERDEU"
    b["status_operacional"] = "FINALIZADA"
    b["finalizada_em"] = agora().strftime("%d/%m/%Y %H:%M:%S")
    b["fonte_finalizacao"] = source
    b["resultado_confirmado"] = result_text or source

    if won:
        b["retorno_real"] = round(stake * odd, 2)
        b["lucro_real"] = round(b["retorno_real"] - stake, 2)
    else:
        b["retorno_real"] = 0.0
        b["lucro_real"] = round(-stake, 2)

    return b


def demo_server_settle_pending(force_reconcile=False):
    """
    Corrige o problema de partidas antigas ficarem para sempre como AO VIVO.

    Fontes de finalização:
      1) Betfair API oficial, se conectada;
      2) BF Bot CSV com vencedor;
      3) SportMonks por Fixture ID;
      4) SportMonks por casamento automático de times + horário.

    Nunca inventa vitória/derrota. Se a partida já saiu do ao vivo mas o
    resultado ainda não chegou, ela sai de "EM ANDAMENTO" e passa a
    "AGUARDANDO CONFIRMAÇÃO FINAL".
    """
    with DEMO_CLOUD_LOCK:
        bets = [dict(x) for x in DEMO_CLOUD_BETS]

    pending = [
        b for b in bets
        if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
    ]
    if not pending:
        return {
            "alteradas": 0,
            "pendentes": 0,
            "em_andamento": 0,
            "aguardando_final": 0,
        }

    market_ids = [
        str(b.get("market_id") or "")
        for b in pending
        if str(b.get("market_id") or "")
    ]

    bf_results = betfair_market_results(market_ids) if _betfair_api_ready() else {}
    csv_results = {
        str(r.get("market_id") or ""): r
        for r in demo_result_rows()
        if str(r.get("market_id") or "")
    }

    pool = _sportmonks_reconcile_pool(force=force_reconcile)
    changed = 0
    linked_now = 0
    by_key = {_demo_bet_key(b): b for b in bets if _demo_bet_key(b)}

    for bet in pending:
        key = _demo_bet_key(bet)
        if not key or key not in by_key:
            continue

        b = by_key[key]
        mid = str(b.get("market_id") or "")

        # ----------------------------------------------------
        # 1) BETFAIR API
        # ----------------------------------------------------
        api = bf_results.get(mid) or {}
        if api.get("ok"):
            b["betfair_market_status"] = api.get("status")
            b["betfair_inplay"] = bool(api.get("inplay"))
            b["betfair_total_matched_atual"] = api.get("total_matched")

            if api.get("status") == "CLOSED":
                winners = api.get("winners") or []
                if winners:
                    sel = _norm_text(b.get("selecao"))
                    won = any(
                        sel == _norm_text(w)
                        or sel in _norm_text(w)
                        or _norm_text(w) in sel
                        for w in winners
                    )
                    _settle_bet_object(
                        b,
                        won,
                        "BETFAIR_API",
                        "Vencedor(es): " + ", ".join(winners),
                    )
                    changed += 1
                    continue

            if api.get("inplay"):
                b["status_operacional"] = "EM ANDAMENTO"
                b["confirmacao_ao_vivo"] = "BETFAIR_API"
                continue

        # ----------------------------------------------------
        # 2) BF BOT CSV
        # ----------------------------------------------------
        csvr = csv_results.get(mid)
        if csvr and csvr.get("winners"):
            winner = _norm_text(csvr.get("winners"))
            sel = _norm_text(b.get("selecao"))
            if winner and sel:
                won = (winner in sel or sel in winner)
                _settle_bet_object(
                    b,
                    won,
                    "BFBOT_CSV",
                    str(csvr.get("winners")),
                )
                changed += 1
                continue

        # ----------------------------------------------------
        # 3/4) SPORTMONKS - ID OU TIMES/HORÁRIO
        # ----------------------------------------------------
        fixture = _match_bet_to_fixture(b, pool)

        if fixture:
            if not b.get("fixture_id"):
                b["fixture_id"] = str(fixture.get("id") or "")
                home, away = participants(fixture)
                b["casa"] = b.get("casa") or home.get("name")
                b["fora"] = b.get("fora") or away.get("name")
                b["liga"] = b.get("liga") or league_name(fixture)
                linked_now += 1

            final = _fixture_final_payload(fixture)

            if final and final.get("finished"):
                won = _selection_won_from_score(b, final)
                if won is not None:
                    score = f"{final.get('home_goals')} x {final.get('away_goals')}"
                    _settle_bet_object(
                        b,
                        bool(won),
                        "SPORTMONKS",
                        score,
                    )
                    changed += 1
                    continue

            if _fixture_is_live_now(fixture, pool):
                b["status_operacional"] = "EM ANDAMENTO"
                b["confirmacao_ao_vivo"] = "SPORTMONKS"
                b["provavelmente_encerrada"] = False
                continue

        # ----------------------------------------------------
        # 5) HORÁRIO: NÃO DEIXA ROLAR 3 HORAS COMO AO VIVO
        # ----------------------------------------------------
        dt = _flex_start_dt(b.get("horario") or b.get("start_time"))
        elapsed = None

        if dt:
            elapsed = (agora() - dt).total_seconds() / 60.0
            b["minutos_desde_inicio"] = round(elapsed, 1)

        if elapsed is not None and elapsed > CONFIG["demo_finish_grace_minutes"]:
            b["status_operacional"] = "AGUARDANDO CONFIRMAÇÃO FINAL"
            b["provavelmente_encerrada"] = True
            b["confirmacao_ao_vivo"] = None
        elif elapsed is not None and elapsed >= 0:
            # Só mantém em andamento quando ainda está dentro da janela razoável.
            b["status_operacional"] = "EM ANDAMENTO"
        else:
            b["status_operacional"] = "AGUARDANDO INÍCIO"

    with DEMO_CLOUD_LOCK:
        DEMO_CLOUD_BETS[:] = list(by_key.values())
        globals()["DEMO_CLOUD_UPDATED_AT"] = agora().isoformat()
        _demo_cloud_save_locked()

    vals = list(by_key.values())
    return {
        "alteradas": changed,
        "vinculadas_sportmonks_agora": linked_now,
        "pendentes": sum(
            1 for b in vals
            if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
        ),
        "em_andamento": sum(
            1 for b in vals
            if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
            and str(b.get("status_operacional") or "") == "EM ANDAMENTO"
        ),
        "aguardando_final": sum(
            1 for b in vals
            if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
            and str(b.get("status_operacional") or "") == "AGUARDANDO CONFIRMAÇÃO FINAL"
        ),
        "reconcile_error": pool.get("error"),
    }


def _demo_server_available_bank(bets):
    initial = float(CONFIG["demo_bank"])
    realized = 0.0
    locked = 0.0
    for b in bets:
        stake = float(b.get("stake") or 0)
        st = str(b.get("status") or "AGUARDANDO RESULTADO")
        if st == "GANHOU":
            realized += float(b.get("lucro_real") or 0)
        elif st == "PERDEU":
            realized -= stake
        elif st in ("CANCELADA", "ANULADA"):
            pass
        else:
            locked += stake
    return initial + realized - locked


def demo_server_open_candidates(candidates):
    if not CONFIG["demo_server_engine"] or not CONFIG["demo_auto_enabled"]:
        return {"criadas": 0}

    with DEMO_CLOUD_LOCK:
        bets = [dict(x) for x in DEMO_CLOUD_BETS]

    existing = {
        str(b.get("demo_key") or "")
        for b in bets if str(b.get("demo_key") or "")
    }
    pending = sum(
        1 for b in bets
        if str(b.get("status") or "") == "AGUARDANDO RESULTADO"
    )
    available = _demo_server_available_bank(bets)
    created = 0

    for c in (candidates or []):
        if pending >= int(CONFIG["demo_max_open"]):
            break

        key = str(c.get("demo_key") or "")
        if not key or key in existing:
            continue

        stake = float(c.get("stake") or CONFIG["demo_stake"])
        odd = float(c.get("odd") or 0)
        if odd <= 1 or available < stake:
            continue

        retorno = round(stake * odd, 2)
        bet = {
            "id": int(time.time() * 1000) + created,
            "demo_key": key,
            "auto_demo": True,
            "modo": "AUTO DEMO",
            "origem_registro": "SERVIDOR MATRIX",
            "market_id": c.get("market_id"),
            "event_id": c.get("event_id"),
            "fixture_id": c.get("fixture_id"),
            "jogo": c.get("jogo"),
            "casa": c.get("casa"),
            "fora": c.get("fora"),
            "liga": c.get("liga") or "Betfair AO VIVO",
            "horario": c.get("start_time") or "",
            "minuto": c.get("minuto"),
            "mercado": c.get("mercado"),
            "market_kind": c.get("market_kind"),
            "selecao": c.get("selecao"),
            "stake": round(stake, 2),
            "odd": round(odd, 2),
            "fonte_odd": "BETFAIR",
            "valor_na_selecao": float(c.get("valor_na_selecao") or 0),
            "total_correspondido": c.get("total_correspondido"),
            "indice_demo": c.get("indice_demo"),
            "forma_recente": c.get("forma_recente"),
            "forma_time_escolhido": c.get("forma_time_escolhido"),
            "forma_vantagem": c.get("forma_vantagem"),
            "forma_confirma_entrada": c.get("forma_confirma_entrada"),
            "prob_implicita": c.get("prob_implicita"),
            "time_favorito_betfair": c.get("time_favorito_betfair") or c.get("selecao"),
            "confirmacao_favorito": bool(c.get("confirmacao_favorito")),
            "retorno": retorno,
            "lucro": round(retorno - stake, 2),
            "motivo": c.get("motivo"),
            "status": "AGUARDANDO RESULTADO",
            "status_operacional": "EM ANDAMENTO",
            "criada_em": agora().strftime("%d/%m/%Y %H:%M:%S"),
        }
        bets.append(bet)
        existing.add(key)
        available -= stake
        pending += 1
        created += 1

    if created:
        _demo_cloud_merge(bets)
    return {"criadas": created}


def demo_server_tick(force=False):
    global DEMO_SERVER_LAST_TICK

    if not CONFIG["demo_server_engine"]:
        return {"ativo": False}

    now_ts = time.time()
    with DEMO_SERVER_TICK_LOCK:
        if (
            not force and DEMO_SERVER_LAST_TICK
            and now_ts - DEMO_SERVER_LAST_TICK < CONFIG["demo_server_tick_seconds"]
        ):
            return {"ativo": True, "cache": True}

        catalog = betfair_catalogue_auto_sync(force=False)
        settled = demo_server_settle_pending(force_reconcile=force)
        snap = demo_auto_snapshot()
        opened = demo_server_open_candidates(snap.get("candidatos") or [])

        DEMO_SERVER_LAST_TICK = time.time()
        return {
            "ativo": True,
            "catalogo": catalog,
            "finalizacao": settled,
            "abertura": opened,
        }


def demo_auto_snapshot():
    c = enrich_demo_candidates_with_runner_volume(demo_live_candidates())
    return {
        "habilitado": CONFIG["demo_auto_enabled"],
        "modo": "DEMONSTRACAO",
        "banca_inicial": CONFIG["demo_bank"],
        "valor_por_entrada": CONFIG["demo_stake"],
        "odd_min": CONFIG["demo_odd_min"],
        "odd_max": CONFIG["demo_odd_max"],
        "liquidez_minima": CONFIG["demo_min_market_liquidity"],
        "valor_minimo_na_selecao": CONFIG["demo_min_selection_value"],
        "minuto_min": CONFIG["demo_min_live_minute"],
        "minuto_max": CONFIG["demo_max_live_minute"],
        "max_por_partida": CONFIG["demo_max_per_event"],
        "max_abertas": CONFIG["demo_max_open"],
        "dados_idade_segundos": betfair_visible_age_seconds(),
        "dados_frescos_para_demo": _demo_visible_fresh_enough(),
        "candidatos": c,
        "total_candidatos": len(c),
        "mercados": [
            "Resultado da partida (Match Odds)",
            "Mais/Menos de 1,5 gols",
            "Mais/Menos de 2,5 gols",
            "Ambas marcam (quando vier no CSV)",
        ],
        "volume_por_selecao_api": _betfair_api_ready(),
        "volume_por_selecao_status": (
            "ATIVO - volume correspondido de cada seleção disponível"
            if _betfair_api_ready()
            else "AGUARDANDO BETFAIR API - o CSV sozinho não separa volume por time"
        ),
        "analise_valor_selecao": True,
        "observacao_valor": (
            "O valor junto ao nome/seleção é liquidez disponível na cotação exibida, "
            "não percentual de pessoas apostando."
        ),
        "observacao": "AUTO DEMO somente. Nenhuma ordem real é enviada pela MATRIX.",
    }


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
        "cearense", "catarinense", "goiano", "alagoano", "paraibano",
        "potiguar", "sergipano", "capixaba", "amazonense", "paraense",
        "pernambuco", "pernambucano", "copa do nordeste"
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



def _forma_label(points, games):
    if games <= 0:
        return "SEM DADOS"
    max_points = games * 3
    ratio = points / max_points if max_points else 0
    if ratio >= 0.84:
        return "MUITO FORTE"
    if ratio >= 0.60:
        return "FORTE"
    if ratio >= 0.40:
        return "REGULAR"
    if ratio > 0:
        return "FRACA"
    return "MUITO FRACA"


def team_recent_form(team_id, team_name, before_dt=None):
    """
    Últimos jogos do time, independentemente do adversário.
    Usa o endpoint SportMonks:
      /fixtures/between/{start_date}/{end_date}/{team_id}

    A força recente é transparente:
      vitória = 3 pontos
      empate  = 1 ponto
      derrota = 0 ponto
    """
    if not team_id:
        return {
            "disponivel": False,
            "time": team_name,
            "jogos": 0,
            "ultimos": [],
            "motivo": "ID do time não disponível.",
        }

    reference = before_dt or agora()
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=TZ)

    cache_key = (int(team_id), reference.strftime("%Y-%m-%d"))
    cached = TEAM_FORM_CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < TEAM_FORM_TTL:
        return cached["data"]

    end_dt = reference - timedelta(seconds=1)
    start_dt = end_dt - timedelta(days=CONFIG["forma_recente_dias"])

    try:
        rows = get_pages(
            f"/fixtures/between/{start_dt.strftime('%Y-%m-%d')}/{end_dt.strftime('%Y-%m-%d')}/{team_id}",
            {"include": "participants;scores;state;league"},
            max_pages=3,
        )
    except Exception as e:
        data = {
            "disponivel": False,
            "time": team_name,
            "jogos": 0,
            "ultimos": [],
            "motivo": str(e),
        }
        TEAM_FORM_CACHE[cache_key] = {"ts": time.time(), "data": data}
        return data

    def sort_key(f):
        dt = parse_dt(f.get("starting_at"))
        return dt.timestamp() if dt else 0

    rows = sorted(rows, key=sort_key, reverse=True)
    last = []

    for f in rows:
        dt = parse_dt(f.get("starting_at"))
        if dt and dt >= reference:
            continue

        home, away = participants(f)
        scores = h2h_score_by_team(f)

        if team_id not in scores:
            continue

        is_home = home.get("id") == team_id
        opp = away if is_home else home
        opp_id = opp.get("id")
        if not opp_id or opp_id not in scores:
            continue

        gf = int(scores.get(team_id, 0))
        ga = int(scores.get(opp_id, 0))

        if gf > ga:
            result = "VITÓRIA"
            points = 3
        elif gf == ga:
            result = "EMPATE"
            points = 1
        else:
            result = "DERROTA"
            points = 0

        last.append({
            "data": dt.strftime("%d/%m/%Y") if dt else "-",
            "adversario": opp.get("name") or "Adversário",
            "local": "CASA" if is_home else "FORA",
            "resultado": result,
            "placar": f"{gf} x {ga}",
            "gols_pro": gf,
            "gols_contra": ga,
            "pontos": points,
            "liga": league_name(f),
        })

        if len(last) >= CONFIG["forma_recente_jogos"]:
            break

    n = len(last)
    if not n:
        data = {
            "disponivel": False,
            "time": team_name,
            "jogos": 0,
            "ultimos": [],
            "motivo": "Sem jogos anteriores com placar disponíveis no período.",
        }
    else:
        points = sum(x["pontos"] for x in last)
        wins = sum(1 for x in last if x["resultado"] == "VITÓRIA")
        draws = sum(1 for x in last if x["resultado"] == "EMPATE")
        losses = sum(1 for x in last if x["resultado"] == "DERROTA")
        gf = sum(x["gols_pro"] for x in last)
        ga = sum(x["gols_contra"] for x in last)
        strength = round(points / (n * 3) * 100, 1)

        data = {
            "disponivel": True,
            "time": team_name,
            "jogos": n,
            "pontos": points,
            "max_pontos": n * 3,
            "vitorias": wins,
            "empates": draws,
            "derrotas": losses,
            "gols_pro": gf,
            "gols_contra": ga,
            "saldo_gols": gf - ga,
            "forca_pct": strength,
            "momento": _forma_label(points, n),
            "ultimos": last,
            "motivo": None,
        }

    TEAM_FORM_CACHE[cache_key] = {"ts": time.time(), "data": data}
    return data


def recent_pair_form(home_id, away_id, home_name, away_name, before_dt=None):
    home_form = team_recent_form(home_id, home_name, before_dt)
    away_form = team_recent_form(away_id, away_name, before_dt)

    hp = home_form.get("pontos", 0) if home_form.get("disponivel") else 0
    ap = away_form.get("pontos", 0) if away_form.get("disponivel") else 0

    # Probabilidades relativas da forma, com suavização para não exagerar
    # apenas dois jogos.
    home_raw = hp + 1
    away_raw = ap + 1
    draw_raw = 2
    total = home_raw + away_raw + draw_raw

    probs = {
        "HOME": home_raw / total,
        "DRAW": draw_raw / total,
        "AWAY": away_raw / total,
    }

    both_full = (
        home_form.get("jogos", 0) >= CONFIG["forma_recente_jogos"]
        and away_form.get("jogos", 0) >= CONFIG["forma_recente_jogos"]
    )
    both_some = home_form.get("jogos", 0) >= 1 and away_form.get("jogos", 0) >= 1

    weight = (
        CONFIG["forma_recente_peso_max"]
        if both_full
        else (CONFIG["forma_recente_peso_max"] / 2 if both_some else 0.0)
    )

    if hp > ap:
        vantagem = home_name
    elif ap > hp:
        vantagem = away_name
    else:
        vantagem = "EQUILIBRADO"

    return {
        "disponivel": bool(both_some),
        "casa": home_form,
        "fora": away_form,
        "probs": probs,
        "peso": weight,
        "vantagem": vantagem,
        "pontos_casa": hp,
        "pontos_fora": ap,
    }


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

    fixture_dt = parse_dt(f.get("starting_at")) or agora()
    forma_recente = recent_pair_form(
        item["casa_id"], item["fora_id"], item["casa"], item["fora"], fixture_dt
    )
    item["forma_recente"] = forma_recente

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

    # V3.20: combina mercado + H2H + forma recente dos ÚLTIMOS 2 jogos.
    # A forma recente tem peso máximo de 20% para não exagerar uma amostra curta.
    recent_weight = float(forma_recente.get("peso") or 0.0)

    h2h_weight = 0.20 if h2h.get("jogos", 0) >= 3 else (0.10 if h2h.get("jogos", 0) else 0.0)

    # Se a forma recente estiver ativa, reduz o peso do H2H antes de tocar
    # no peso principal do mercado.
    total_aux = h2h_weight + recent_weight
    if total_aux > 0.40:
        scale = 0.40 / total_aux
        h2h_weight *= scale
        recent_weight *= scale

    market_weight = 1.0 - h2h_weight - recent_weight

    scored = {}
    for key, value in market.items():
        hist_prob = (h2h.get("probs") or {}).get(key, value["market_prob"])
        recent_prob = (forma_recente.get("probs") or {}).get(key, value["market_prob"])
        combined = (
            market_weight * value["market_prob"]
            + h2h_weight * hist_prob
            + recent_weight * recent_prob
        )
        scored[key] = {
            **value,
            "hist_prob": hist_prob,
            "recent_prob": recent_prob,
            "combined": combined,
        }

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
        "peso_forma_recente": round(recent_weight * 100, 0),
        "prob_forma_recente": round(v["recent_prob"] * 100, 1),
        "forma_recente": forma_recente,
        "stake_padrao": round(stake, 2),
        "retorno_potencial_padrao": round(potential_return, 2),
        "lucro_potencial_padrao": round(potential_profit, 2),
        "h2h": h2h,
        "status": "APROVADO" if approved else "AGUARDAR",
        "motivo": "Passou pelos filtros de odds + H2H + forma recente dos últimos 2 jogos." if approved else "; ".join(reasons),
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

        # Brasil recebe prioridade para não ser cortado quando houver
        # muitos jogos internacionais no retorno.
        all_futures = list(futures)
        brazil_first = [f for f in all_futures if is_brazilian(f)]
        others = [f for f in all_futures if not is_brazilian(f)]
        futures = (brazil_first + others)[:240]

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
        brasileiros = [
            x for x in todos
            if _norm_text(x.get("pais")) in ("brazil", "brasil")
            or any(t in _norm_text(x.get("liga")) for t in (
                "brasileir", "copa do brasil", "paulista", "carioca",
                "mineiro", "gaucho", "paranaense", "baiano", "pernambucano",
                "pernambuco", "cearense", "catarinense", "goiano",
                "copa do nordeste", "paraibano", "alagoano", "potiguar"
            ))
        ]

        with LOCK:
            STATE.update({
                "status": "online",
                "ultima_atualizacao": agora().isoformat(timespec="seconds"),
                "jogos_encontrados": len(futures),
                "jogos_com_odds": with_odds,
                "jogos_analisados": analyzed,
                "libertadores": libertadores,
                "internacionais": internacionais,
                "brasileiros": brasileiros,
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

        # A análise pode usar SportMonks/H2H, mas a execução só usa odd BETFAIR.
        bf_odd = _betfair_odd_for_signal(s)
        if not bf_odd.get("ok"):
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
    _demo_cloud_load()
    threading.Thread(target=worker, daemon=True).start()

    def demo_engine_loop():
        while True:
            try:
                demo_server_tick(force=False)
            except Exception:
                pass
            time.sleep(max(5, CONFIG["demo_server_tick_seconds"]))

    threading.Thread(target=demo_engine_loop, daemon=True).start()


@app.get("/api/status")
def status():
    # Copia o estado rapidamente e libera o lock antes de calcular o feed BFBOT.
    # Isso evita o travamento que deixava o painel em "..." e todos os contadores em 0.
    with LOCK:
        state_copy = dict(STATE)
        state_copy["sinais"] = [dict(x) for x in (STATE.get("sinais") or [])]
        state_copy["internacionais"] = [dict(x) for x in (STATE.get("internacionais") or [])]
        state_copy["libertadores"] = [dict(x) for x in (STATE.get("libertadores") or [])]
        state_copy["brasileiros"] = [dict(x) for x in (STATE.get("brasileiros") or [])]

    # Acrescenta a odd BETFAIR aos cards sem substituir os dados de análise.
    enriched_by_fixture = {}
    for group in ("sinais", "internacionais", "libertadores"):
        for s in state_copy.get(group) or []:
            bf = _betfair_odd_for_signal(s)
            s["odd_betfair"] = bf.get("odd")
            s["odd_betfair_ok"] = bool(bf.get("ok"))
            s["odd_betfair_fresca"] = bool(bf.get("fresca"))
            s["odd_betfair_fonte"] = bf.get("fonte")
            s["odd_betfair_motivo"] = bf.get("motivo")
            s["odd_betfair_selecao"] = bf.get("favorite_selection")
            if s.get("fixture_id") is not None:
                enriched_by_fixture[str(s.get("fixture_id"))] = bf

    server_engine = demo_server_tick(force=False)
    tips = bfbot_tips()

    return JSONResponse({
        "nome": "MATRIX - FUTEBOL",
        "versao": "V3.22 AO VIVO REAL + FINALIZACAO AUTOMATICA + RECONCILIACAO",
        "config": CONFIG,
        "conta": account_info(),
        "betfair_mirror": betfair_mirror_snapshot(),
        "betfair_ao_vivo": betfair_live_payload(),
        "demo_auto": demo_auto_snapshot(),
        "demo_resultados": demo_result_rows(),
        "demo_cloud": demo_cloud_snapshot(),
        "demo_server_engine": server_engine,
        "betfair_api": {
            "conectada": _betfair_api_ready(),
            "catalogo_sem_filtro_pais": True,
            "inclui_brasil_quando_disponivel": True,
        },
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



@app.get("/api/demo-bets")
def get_demo_bets_cloud():
    return JSONResponse(demo_cloud_snapshot())


@app.post("/api/demo-bets/sync")
async def sync_demo_bets_cloud(request: Request):
    """
    Une o histórico local enviado por notebook/celular ao histórico do servidor
    e devolve uma lista canônica para TODOS os aparelhos.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    incoming = payload.get("bets") if isinstance(payload, dict) else []
    if not isinstance(incoming, list):
        return JSONResponse(
            {"ok": False, "erro": "Campo bets deve ser uma lista."},
            status_code=400,
        )

    merged = _demo_cloud_merge(incoming)
    snap = demo_cloud_snapshot()
    snap["bets"] = merged
    return JSONResponse(snap)


@app.post("/api/analisar")
def analisar():
    run_analysis()
    demo_server_tick(force=True)
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
    return {"ok": True, "versao": "3.22", "servidor_unico": True, "reconciliacao": True}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(
        (STATIC / "index.html").read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Matrix-Version": "3.22",
        },
    )
