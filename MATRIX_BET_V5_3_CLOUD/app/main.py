
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine, String, Integer, Float, Text, ForeignKey,
    select, delete
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

BASE = Path(__file__).resolve().parent.parent
FRONTEND = BASE / "frontend"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{BASE / 'matrix_v53.db'}"

# Some providers still expose postgres://; SQLAlchemy expects postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    demo_balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=25000)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

class Bet(Base):
    __tablename__ = "bets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    stake_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_odd: Mapped[float] = mapped_column(Float, nullable=False)
    potential_return_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    selections_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MATRIX BET V5.3 CLOUD API", version="5.3.0")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return dk.hex()

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def audit(db: Session, user_id: Optional[int], action: str, details: str = ""):
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        details=details[:1000],
        created_at=now_iso()
    ))

def create_session(db: Session, user_id: int) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    db.add(SessionToken(
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires.isoformat(),
        created_at=now_iso()
    ))
    return raw

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db)
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Não autenticado")
    raw = authorization[7:].strip()
    st = db.get(SessionToken, hash_token(raw))
    if not st:
        raise HTTPException(401, "Sessão inválida")
    if datetime.fromisoformat(st.expires_at) < datetime.now(timezone.utc):
        db.delete(st)
        db.commit()
        raise HTTPException(401, "Sessão expirada")
    user = db.get(User, st.user_id)
    if not user:
        raise HTTPException(401, "Usuário inexistente")
    return user

_ATTEMPTS: dict[str, list[float]] = {}
def rate_limit(request: Request, bucket: str, limit: int = 12, window: int = 60):
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    key = f"{bucket}:{ip}"
    now = time.time()
    arr = [t for t in _ATTEMPTS.get(key, []) if now - t < window]
    if len(arr) >= limit:
        raise HTTPException(429, "Muitas tentativas. Aguarde um minuto.")
    arr.append(now)
    _ATTEMPTS[key] = arr

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class SelectionIn(BaseModel):
    event_id: str
    market: str
    pick: str
    odd: float = Field(gt=1.0, lt=1000)

class BetIn(BaseModel):
    stake_cents: int = Field(ge=100, le=1000000)
    selections: list[SelectionIn] = Field(min_length=1, max_length=20)

PREGAME = [
    {"id":"br-a-1","league":"Brasileirão Série A","time":"19:00","home":"Palmeiras","away":"Flamengo","odds":{"1":2.10,"X":3.25,"2":3.40}},
    {"id":"br-a-2","league":"Brasileirão Série A","time":"21:30","home":"Atlético MG","away":"Corinthians","odds":{"1":2.35,"X":3.10,"2":3.05}},
    {"id":"br-b-1","league":"Brasileirão Série B","time":"20:00","home":"Goiás","away":"Criciúma","odds":{"1":2.05,"X":3.15,"2":3.60}},
    {"id":"lib-1","league":"Libertadores","time":"21:30","home":"River Plate","away":"Flamengo","odds":{"1":2.10,"X":3.30,"2":3.40}},
    {"id":"ucl-1","league":"Champions League","time":"17:00","home":"Real Madrid","away":"Manchester City","odds":{"1":2.15,"X":3.40,"2":3.10}},
    {"id":"epl-1","league":"Premier League","time":"16:00","home":"Chelsea","away":"Arsenal","odds":{"1":2.35,"X":3.50,"2":2.90}},
    {"id":"laliga-1","league":"LaLiga","time":"16:30","home":"Barcelona","away":"Sevilla","odds":{"1":1.62,"X":4.10,"2":5.20}},
    {"id":"seriea-1","league":"Serie A","time":"15:45","home":"Inter","away":"Juventus","odds":{"1":2.05,"X":3.20,"2":3.65}},
    {"id":"bund-1","league":"Bundesliga","time":"13:30","home":"Bayern München","away":"Dortmund","odds":{"1":1.65,"X":4.15,"2":4.60}},
]
EVENT_LOOKUP = {e["id"]: e for e in PREGAME}

def make_live():
    pairs = [
        ("Palmeiras","Flamengo","Brasileirão Série A"),
        ("Real Madrid","Barcelona","LaLiga"),
        ("Inter","Juventus","Serie A"),
        ("Manchester City","Arsenal","Premier League"),
        ("River Plate","Boca Juniors","Libertadores"),
    ]
    arr = []
    for i in range(136):
        h,a,l = pairs[i % len(pairs)]
        arr.append({
            "id": f"live-{i+1}",
            "league": l,
            "time": f"{10 + (i*7)%80}'",
            "home": h,
            "away": a,
            "score": f"{i%3} - {(i+1)%3}",
            "odds": {
                "1": round(1.35 + (i%9)*0.15,2),
                "X": round(2.75 + (i%6)*0.20,2),
                "2": round(1.70 + (i%8)*0.25,2),
            }
        })
    return arr

LIVE = make_live()
LIVE_LOOKUP = {e["id"]: e for e in LIVE}

@app.get("/health")
def health():
    return {
        "ok": True,
        "version": "5.3.0",
        "database": "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite"
    }

@app.post("/api/auth/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "register", 8, 60)
    email = data.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(409, "E-mail já cadastrado")
    salt = secrets.token_hex(16)
    user = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password, salt),
        salt=salt,
        demo_balance_cents=25000,
        created_at=now_iso()
    )
    db.add(user)
    db.flush()
    token = create_session(db, user.id)
    audit(db, user.id, "REGISTER", email)
    db.commit()
    return {
        "token": token,
        "user": {
            "id":user.id,"name":user.name,"email":user.email,
            "demo_balance_cents":user.demo_balance_cents
        }
    }

@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "login", 12, 60)
    email = data.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(401, "E-mail ou senha inválidos")
    candidate = hash_password(data.password, user.salt)
    if not hmac.compare_digest(candidate, user.password_hash):
        audit(db, user.id, "LOGIN_FAILED", email)
        db.commit()
        raise HTTPException(401, "E-mail ou senha inválidos")
    token = create_session(db, user.id)
    audit(db, user.id, "LOGIN_OK", email)
    db.commit()
    return {
        "token": token,
        "user": {
            "id":user.id,"name":user.name,"email":user.email,
            "demo_balance_cents":user.demo_balance_cents
        }
    }

@app.post("/api/auth/logout")
def logout(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db)
):
    if authorization.startswith("Bearer "):
        token_hash = hash_token(authorization[7:].strip())
        st = db.get(SessionToken, token_hash)
        if st:
            db.delete(st)
            db.commit()
    return {"ok": True}

@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id":user.id,"name":user.name,"email":user.email,
        "demo_balance_cents":user.demo_balance_cents
    }

@app.get("/api/events")
def events(user: User = Depends(get_current_user)):
    return {"events": PREGAME}

@app.get("/api/live")
def get_live(user: User = Depends(get_current_user)):
    return {"count": len(LIVE), "events": LIVE}

@app.get("/api/bets")
def get_bets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(Bet).where(Bet.user_id == user.id).order_by(Bet.id.desc()).limit(100)
    ).all()
    return {
        "bets": [{
            "id":r.id,"stake_cents":r.stake_cents,"total_odd":r.total_odd,
            "potential_return_cents":r.potential_return_cents,
            "selections_json":r.selections_json,"status":r.status,
            "created_at":r.created_at
        } for r in rows]
    }

@app.post("/api/bets")
def place_bet(
    data: BetIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_odd = 1.0
    clean = []
    for s in data.selections:
        event = EVENT_LOOKUP.get(s.event_id) or LIVE_LOOKUP.get(s.event_id)
        if not event:
            raise HTTPException(400, f"Evento inválido: {s.event_id}")
        server_odd = event["odds"].get(s.pick)
        if server_odd is None:
            raise HTTPException(400, f"Seleção inválida: {s.pick}")
        total_odd *= float(server_odd)
        clean.append({
            "event_id":s.event_id,
            "league":event["league"],
            "home":event["home"],
            "away":event["away"],
            "market":s.market,
            "pick":s.pick,
            "odd":server_odd
        })

    # reload within current session
    user_db = db.get(User, user.id)
    if user_db.demo_balance_cents < data.stake_cents:
        raise HTTPException(400, "Saldo demo insuficiente")

    potential = int(round(data.stake_cents * total_odd))
    user_db.demo_balance_cents -= data.stake_cents
    bet = Bet(
        user_id=user.id,
        stake_cents=data.stake_cents,
        total_odd=total_odd,
        potential_return_cents=potential,
        selections_json=json.dumps(clean, ensure_ascii=False),
        status="OPEN",
        created_at=now_iso()
    )
    db.add(bet)
    db.flush()
    audit(db, user.id, "BET_DEMO_PLACED", f"id={bet.id};stake={data.stake_cents}")
    db.commit()
    return {
        "ok":True,
        "bet_id":bet.id,
        "total_odd":round(total_odd,4),
        "potential_return_cents":potential
    }

@app.post("/api/demo/add-balance")
def add_demo_balance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_db = db.get(User, user.id)
    user_db.demo_balance_cents += 10000
    audit(db, user.id, "DEMO_BALANCE_ADD", "+10000")
    db.commit()
    db.refresh(user_db)
    return {"demo_balance_cents":user_db.demo_balance_cents}

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
