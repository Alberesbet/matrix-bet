
from __future__ import annotations
import requests

import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from email.message import EmailMessage

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine, String, Integer, Float, Text, ForeignKey,
    select, delete, text
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
engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
    "connect_args": connect_args,
}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update({"pool_recycle": 300, "pool_size": 5, "max_overflow": 5})
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    cpf_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cpf_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    is_admin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avatar_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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


class UserPaymentAccount(Base):
    __tablename__ = "user_payment_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False, index=True)
    holder_name: Mapped[str] = mapped_column(String(120), nullable=False)
    holder_cpf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pix_key: Mapped[str] = mapped_column(String(180), nullable=False)
    verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")

class PixCharge(Base):
    __tablename__ = "pix_charges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    txid: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    pix_copy_paste: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    paid_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # deposit / withdrawal
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    pix_key: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    receipt_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    decided_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    admin_reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

Base.metadata.create_all(bind=engine)

def ensure_user_columns():
    """Migração simples e compatível com a base existente."""
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
            if "cpf_hash" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN cpf_hash VARCHAR(64)"))
            if "cpf_last4" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN cpf_last4 VARCHAR(4)"))
            if "is_admin" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"))
            if "is_blocked" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"))
            if "avatar_data" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_data TEXT"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_cpf_hash ON users(cpf_hash)"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cpf_hash VARCHAR(64)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cpf_last4 VARCHAR(4)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data TEXT"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_cpf_hash ON users(cpf_hash)"))

ensure_user_columns()

app = FastAPI(title="MATRIX BET V6.7 SPORTMONKS REAL API", version="6.8.0")

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

def only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())

def valid_cpf(value: str) -> bool:
    cpf = only_digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(x) for x in cpf]
    total = sum(nums[i] * (10 - i) for i in range(9))
    d1 = (total * 10) % 11
    if d1 == 10:
        d1 = 0
    if d1 != nums[9]:
        return False
    total = sum(nums[i] * (11 - i) for i in range(10))
    d2 = (total * 10) % 11
    if d2 == 10:
        d2 = 0
    return d2 == nums[10]

def cpf_digest(value: str) -> str:
    # CPF é dado pessoal sensível; não salvamos o número completo em texto puro.
    return hashlib.sha256(("MATRIXBET-CPF-V1:" + only_digits(value)).encode("utf-8")).hexdigest()

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


def send_email(to_email: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username).strip()
    if not host or not username or not password or not sender:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        return False

def get_admin_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db)
):
    user = get_current_user(authorization, db)
    if not user.is_admin:
        raise HTTPException(403, "Acesso administrativo negado")
    return user

def ensure_admin_account():
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    name = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    if not email or not password or len(password) < 8:
        return
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.is_admin = 1
            db.commit()
            return
        salt = secrets.token_hex(16)
        user = User(
            name=name,
            email=email,
            cpf_hash=None,
            cpf_last4=None,
            is_admin=1,
            is_blocked=0,
            password_hash=hash_password(password, salt),
            salt=salt,
            demo_balance_cents=0,
            created_at=now_iso()
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

ensure_admin_account()

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
    if user.is_blocked:
        raise HTTPException(403, "Conta bloqueada. Entre em contato com o suporte.")
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
    name: str = Field(min_length=3, max_length=30)
    email: EmailStr
    cpf: str = Field(min_length=11, max_length=18)
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

class ChangeEmailIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    new_email: EmailStr

class AvatarIn(BaseModel):
    avatar_data: str = Field(max_length=500000)

class ResetRequestIn(BaseModel):
    email: EmailStr

class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)

class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=80)
    message: str = Field(min_length=5, max_length=2000)

class TicketReplyIn(BaseModel):
    reply: str = Field(min_length=1, max_length=3000)
    status: str = Field(default="IN_PROGRESS", max_length=24)

class AdminSetupIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserAdminUpdateIn(BaseModel):
    is_blocked: bool

class UserBalanceAdminIn(BaseModel):
    demo_balance_cents: int = Field(ge=0, le=100000000)

class SelectionIn(BaseModel):
    event_id: str
    market: str
    pick: str
    odd: float = Field(gt=1.0, lt=1000)

class BetIn(BaseModel):
    stake_cents: int = Field(ge=100, le=1000000)
    selections: list[SelectionIn] = Field(min_length=1, max_length=20)

PREGAME = [
    {"id":"br-a-1","sport":"Futebol","league":"Brasileirão Série A","time":"16:00","home":"Palmeiras","away":"Flamengo","odds":{"1":2.10,"X":3.25,"2":3.40}},
    {"id":"br-a-2","sport":"Futebol","league":"Brasileirão Série A","time":"18:30","home":"Atlético-MG","away":"Corinthians","odds":{"1":2.35,"X":3.10,"2":3.05}},
    {"id":"br-a-3","sport":"Futebol","league":"Brasileirão Série A","time":"20:00","home":"São Paulo","away":"Grêmio","odds":{"1":1.98,"X":3.35,"2":3.85}},
    {"id":"br-b-1","sport":"Futebol","league":"Brasileirão Série B","time":"19:00","home":"Goiás","away":"Criciúma","odds":{"1":2.05,"X":3.15,"2":3.60}},
    {"id":"lib-1","sport":"Futebol","league":"Libertadores","time":"21:30","home":"River Plate","away":"Flamengo","odds":{"1":2.10,"X":3.30,"2":3.40}},
    {"id":"lib-2","sport":"Futebol","league":"Libertadores","time":"21:30","home":"Boca Juniors","away":"Palmeiras","odds":{"1":2.45,"X":3.10,"2":2.95}},
    {"id":"ucl-1","sport":"Futebol","league":"Champions League","time":"17:00","home":"Real Madrid","away":"Manchester City","odds":{"1":2.15,"X":3.40,"2":3.10}},
    {"id":"ucl-2","sport":"Futebol","league":"Champions League","time":"17:00","home":"Bayern München","away":"Paris SG","odds":{"1":2.00,"X":3.65,"2":3.45}},
    {"id":"epl-1","sport":"Futebol","league":"Premier League","time":"16:00","home":"Chelsea","away":"Arsenal","odds":{"1":2.35,"X":3.50,"2":2.90}},
    {"id":"epl-2","sport":"Futebol","league":"Premier League","time":"13:30","home":"Liverpool","away":"Tottenham","odds":{"1":1.70,"X":4.10,"2":4.30}},
    {"id":"laliga-1","sport":"Futebol","league":"LaLiga","time":"16:30","home":"Barcelona","away":"Sevilla","odds":{"1":1.62,"X":4.10,"2":5.20}},
    {"id":"laliga-2","sport":"Futebol","league":"LaLiga","time":"14:00","home":"Atlético de Madrid","away":"Valencia","odds":{"1":1.78,"X":3.60,"2":4.75}},
    {"id":"ita-1","sport":"Futebol","league":"Serie A","time":"15:45","home":"Inter","away":"Juventus","odds":{"1":2.05,"X":3.20,"2":3.65}},
    {"id":"bund-1","sport":"Futebol","league":"Bundesliga","time":"13:30","home":"Bayern München","away":"Dortmund","odds":{"1":1.65,"X":4.15,"2":4.60}},
    {"id":"fra-1","sport":"Futebol","league":"Ligue 1","time":"16:00","home":"Paris SG","away":"Marseille","odds":{"1":1.55,"X":4.30,"2":5.50}},
    {"id":"por-1","sport":"Futebol","league":"Primeira Liga","time":"17:15","home":"Benfica","away":"Porto","odds":{"1":2.20,"X":3.25,"2":3.15}},
    {"id":"arg-1","sport":"Futebol","league":"Liga Argentina","time":"22:00","home":"Racing","away":"Independiente","odds":{"1":2.30,"X":3.00,"2":3.30}},
    {"id":"mls-1","sport":"Futebol","league":"MLS","time":"23:30","home":"Inter Miami","away":"LA Galaxy","odds":{"1":1.88,"X":3.80,"2":3.70}},
]

def build_demo_markets(event):
    eid = str(event.get("id",""))
    seed = sum(ord(c) for c in eid)
    def odd(base, mod=7, step=0.11):
        return round(base + (seed % mod) * step, 2)
    markets = [
        {"group":"Resultado","items":[
            {"market":"Resultado Final","pick":"1","label":"Casa","odd":float(event["odds"]["1"])},
            {"market":"Resultado Final","pick":"X","label":"Empate","odd":float(event["odds"]["X"])},
            {"market":"Resultado Final","pick":"2","label":"Fora","odd":float(event["odds"]["2"])},
            {"market":"Dupla Chance","pick":"1X","label":"Casa ou Empate","odd":odd(1.20,5,0.08)},
            {"market":"Dupla Chance","pick":"12","label":"Casa ou Fora","odd":odd(1.28,5,0.07)},
            {"market":"Dupla Chance","pick":"X2","label":"Empate ou Fora","odd":odd(1.25,5,0.08)},
        ]},
        {"group":"Gols","items":[
            {"market":"Total de Gols","pick":"over_1_5","label":"Mais de 1.5","odd":odd(1.35,6,0.07)},
            {"market":"Total de Gols","pick":"under_1_5","label":"Menos de 1.5","odd":odd(2.30,6,0.12)},
            {"market":"Total de Gols","pick":"over_2_5","label":"Mais de 2.5","odd":odd(1.75,6,0.10)},
            {"market":"Total de Gols","pick":"under_2_5","label":"Menos de 2.5","odd":odd(1.85,6,0.09)},
            {"market":"Ambas Marcam","pick":"btts_yes","label":"Sim","odd":odd(1.65,5,0.10)},
            {"market":"Ambas Marcam","pick":"btts_no","label":"Não","odd":odd(1.80,5,0.11)},
            {"market":"Primeiro Gol","pick":"first_goal_home","label":"Casa","odd":odd(1.85,6,0.13)},
            {"market":"Primeiro Gol","pick":"first_goal_away","label":"Fora","odd":odd(2.10,6,0.14)},
            {"market":"Primeiro Gol","pick":"first_goal_none","label":"Sem gol","odd":odd(7.50,5,0.45)},
        ]},
        {"group":"Handicap","items":[
            {"market":"Handicap","pick":"home_-0_5","label":"Casa -0.5","odd":odd(1.85,6,0.10)},
            {"market":"Handicap","pick":"away_+0_5","label":"Fora +0.5","odd":odd(1.75,6,0.09)},
            {"market":"Handicap","pick":"home_-1_0","label":"Casa -1.0","odd":odd(2.35,6,0.13)},
            {"market":"Handicap","pick":"away_+1_0","label":"Fora +1.0","odd":odd(1.50,6,0.08)},
            {"market":"Handicap","pick":"home_+0_5","label":"Casa +0.5","odd":odd(1.38,6,0.06)},
            {"market":"Handicap","pick":"away_-0_5","label":"Fora -0.5","odd":odd(2.20,6,0.12)},
        ]},
        {"group":"Escanteios","items":[
            {"market":"Total de Escanteios","pick":"corners_over_7_5","label":"Mais de 7.5","odd":odd(1.55,6,0.08)},
            {"market":"Total de Escanteios","pick":"corners_over_9_5","label":"Mais de 9.5","odd":odd(1.95,6,0.11)},
            {"market":"Total de Escanteios","pick":"corners_under_9_5","label":"Menos de 9.5","odd":odd(1.70,6,0.09)},
            {"market":"Mais Escanteios","pick":"corners_home","label":"Casa","odd":odd(1.75,5,0.12)},
            {"market":"Mais Escanteios","pick":"corners_away","label":"Fora","odd":odd(1.95,5,0.13)},
        ]},
        {"group":"Cartões","items":[
            {"market":"Total de Cartões","pick":"cards_over_3_5","label":"Mais de 3.5","odd":odd(1.55,6,0.08)},
            {"market":"Total de Cartões","pick":"cards_over_5_5","label":"Mais de 5.5","odd":odd(2.05,6,0.12)},
            {"market":"Mais Cartões","pick":"cards_home","label":"Casa","odd":odd(1.90,5,0.11)},
            {"market":"Mais Cartões","pick":"cards_away","label":"Fora","odd":odd(1.90,5,0.11)},
        ]},
        {"group":"Faltas","items":[
            {"market":"Total de Faltas","pick":"fouls_over_21_5","label":"Mais de 21.5","odd":odd(1.65,6,0.08)},
            {"market":"Total de Faltas","pick":"fouls_under_21_5","label":"Menos de 21.5","odd":odd(1.95,6,0.08)},
            {"market":"Mais Faltas","pick":"fouls_home","label":"Casa","odd":odd(1.88,5,0.10)},
            {"market":"Mais Faltas","pick":"fouls_away","label":"Fora","odd":odd(1.88,5,0.10)},
        ]},
        {"group":"Pênalti","items":[
            {"market":"Pênalti na Partida","pick":"penalty_yes","label":"Sim","odd":odd(2.55,6,0.25)},
            {"market":"Pênalti na Partida","pick":"penalty_no","label":"Não","odd":odd(1.28,5,0.06)},
            {"market":"Gol de Pênalti","pick":"penalty_goal_yes","label":"Sim","odd":odd(3.10,6,0.28)},
            {"market":"Gol de Pênalti","pick":"penalty_goal_no","label":"Não","odd":odd(1.20,5,0.05)},
        ]},
        {"group":"1º Tempo","items":[
            {"market":"Resultado 1º Tempo","pick":"ht_1","label":"Casa","odd":odd(2.15,6,0.14)},
            {"market":"Resultado 1º Tempo","pick":"ht_X","label":"Empate","odd":odd(1.95,6,0.11)},
            {"market":"Resultado 1º Tempo","pick":"ht_2","label":"Fora","odd":odd(2.45,6,0.15)},
            {"market":"Gol 1º Tempo","pick":"ht_goal_yes","label":"Sim","odd":odd(1.45,6,0.08)},
            {"market":"Gol 1º Tempo","pick":"ht_goal_no","label":"Não","odd":odd(2.40,6,0.13)},
        ]},
    ]
    return markets

def demo_market_lookup(event):
    lookup={}
    for grp in build_demo_markets(event):
        for item in grp["items"]:
            lookup[(item["market"],item["pick"])] = float(item["odd"])
    return lookup

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


SPORTMONKS_BASE = "https://api.sportmonks.com/v3/football"

def _sm_token():
    token = os.getenv("SPORTMONKS_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "SPORTMONKS_TOKEN não configurado no Render.")
    return token

def _sm_get(path: str, params=None):
    params = dict(params or {})
    params["api_token"] = _sm_token()
    try:
        response = requests.get(
            f"{SPORTMONKS_BASE}{path}",
            params=params,
            timeout=20,
            headers={"Accept": "application/json"}
        )
    except requests.RequestException as exc:
        raise HTTPException(502, f"Falha ao consultar Sportmonks: {exc}")
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, "Resposta inválida da Sportmonks.")
    if response.status_code >= 400:
        message = payload.get("message") if isinstance(payload, dict) else None
        raise HTTPException(response.status_code, message or "Erro retornado pela Sportmonks.")
    return payload

def _map_fixture(f):
    home, away = {}, {}
    for p in f.get("participants") or []:
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        item = {
            "id": p.get("id"),
            "name": p.get("name"),
            "image_path": p.get("image_path"),
        }
        if loc == "home":
            home = item
        elif loc == "away":
            away = item

    if not home or not away:
        bits = re.split(r"\s+vs\s+|\s+v\s+", f.get("name") or "", maxsplit=1, flags=re.I)
        if not home and bits:
            home = {"name": bits[0].strip()}
        if not away and len(bits) > 1:
            away = {"name": bits[1].strip()}

    league = f.get("league") or {}
    state = f.get("state") or {}
    return {
        "id": str(f.get("id")),
        "name": f.get("name"),
        "starting_at": f.get("starting_at"),
        "home": home,
        "away": away,
        "league": {
            "id": league.get("id") or f.get("league_id"),
            "name": league.get("name"),
            "image_path": league.get("image_path"),
        },
        "state": {
            "id": state.get("id") or f.get("state_id"),
            "name": state.get("name"),
            "short_name": state.get("short_name"),
        },
        "has_odds": bool(f.get("has_odds")),
        "has_premium_odds": bool(f.get("has_premium_odds")),
        "result_info": f.get("result_info"),
    }

@app.get("/api/real/status")
def real_feed_status(user: User = Depends(get_current_user)):
    return {
        "provider": "Sportmonks",
        "configured": bool(os.getenv("SPORTMONKS_TOKEN", "").strip()),
        "version": "6.8.0"
    }

@app.get("/api/real/fixtures")
def real_fixtures(date: str | None = None, user: User = Depends(get_current_user)):
    from datetime import datetime, timezone
    day = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = _sm_get(
        f"/fixtures/between/{day}/{day}",
        {"include": "participants;league;state"}
    )
    rows = [_map_fixture(x) for x in payload.get("data", [])]
    return {
        "provider": "Sportmonks",
        "date": day,
        "count": len(rows),
        "fixtures": rows,
    }

@app.get("/api/real/fixtures/{fixture_id}/odds")
def real_fixture_odds(fixture_id: int, user: User = Depends(get_current_user)):
    payload = _sm_get(
        f"/odds/pre-match/fixtures/{fixture_id}",
        {"include": "market;bookmaker"}
    )
    return {
        "provider": "Sportmonks",
        "fixture_id": fixture_id,
        "count": len(payload.get("data", [])),
        "odds": payload.get("data", []),
    }

@app.get("/api/real/inplay")
def real_inplay_odds(user: User = Depends(get_current_user)):
    payload = _sm_get(
        "/odds/inplay",
        {"include": "market;bookmaker"}
    )
    return {
        "provider": "Sportmonks",
        "count": len(payload.get("data", [])),
        "odds": payload.get("data", []),
    }


@app.get("/health")
def health():
    db_ok = True
    db_error = ""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = exc.__class__.__name__
    return {
        "ok": db_ok,
        "version": "6.8.0",
        "database": "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite",
        "persistent_database": DATABASE_URL.startswith("postgresql"),
        "db_error": db_error,
    }

@app.post("/api/auth/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "register", 8, 60)

    username = data.name.strip()
    if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9._-]{3,30}", username):
        raise HTTPException(422, "Nome de usuário: use 3 a 30 caracteres, sem espaços; letras, números, ponto, _ ou -")

    email = data.email.lower().strip()
    cpf = only_digits(data.cpf)

    if not valid_cpf(cpf):
        raise HTTPException(422, "CPF inválido")

    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(409, "E-mail já cadastrado")

    existing_name = db.scalar(select(User).where(User.name.ilike(username)))
    if existing_name:
        raise HTTPException(409, "Nome de usuário já está em uso")

    c_hash = cpf_digest(cpf)
    existing_cpf = db.scalar(select(User).where(User.cpf_hash == c_hash))
    if existing_cpf:
        raise HTTPException(409, "CPF já cadastrado")

    salt = secrets.token_hex(16)
    user = User(
        name=username,
        email=email,
        cpf_hash=c_hash,
        cpf_last4=cpf[-4:],
        password_hash=hash_password(data.password, salt),
        salt=salt,
        demo_balance_cents=25000,
        created_at=now_iso()
    )
    db.add(user)
    db.flush()
    token = create_session(db, user.id)
    audit(db, user.id, "REGISTER", f"{email}; CPF final {cpf[-4:]}")
    db.commit()
    return {
        "token": token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "cpf_masked": "***.***.***-" + user.cpf_last4[-2:],
            "demo_balance_cents": user.demo_balance_cents
        }
    }

@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "login", 12, 60)
    email = data.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(401, "E-mail ou senha inválidos")
    if user.is_blocked:
        raise HTTPException(403, "Conta bloqueada. Entre em contato com o suporte.")
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
        "id":user.id,
        "name":user.name,
        "email":user.email,
        "cpf_masked": ("***.***.***-" + user.cpf_last4[-2:]) if user.cpf_last4 else "—",
        "avatar_data": user.avatar_data or "",
        "created_at": user.created_at,
        "is_blocked": bool(user.is_blocked),
        "demo_balance_cents":user.demo_balance_cents
    }

@app.get("/api/events")
def events(user: User = Depends(get_current_user)):
    return {"events": [{**e, "markets": build_demo_markets(e)} for e in PREGAME]}

@app.get("/api/live")
def get_live(user: User = Depends(get_current_user)):
    return {"count": len(LIVE), "events": LIVE}


@app.get("/api/events/{event_id}/markets")
def event_markets(event_id: str, user: User = Depends(get_current_user)):
    event = EVENT_LOOKUP.get(event_id) or LIVE_LOOKUP.get(event_id)
    if not event:
        raise HTTPException(404, "Evento não encontrado")
    return {"event":event,"groups":build_demo_markets(event)}

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
        market_lookup = demo_market_lookup(event)
        server_odd = market_lookup.get((s.market, s.pick))
        if server_odd is None:
            raise HTTPException(400, f"Seleção inválida: {s.market} / {s.pick}")
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




# ---------- PIX Sandbox / Provider-ready ----------
def payment_mode() -> str:
    return os.getenv("PAYMENTS_MODE", "sandbox").strip().lower()

def _payment_account(db: Session, user_id: int):
    return db.scalar(select(UserPaymentAccount).where(UserPaymentAccount.user_id == user_id))

@app.get("/api/payments/status")
def payments_status():
    return {
        "mode": payment_mode(),
        "live_enabled": False,
        "provider": os.getenv("PIX_PROVIDER", "sandbox"),
        "message": "Modo sandbox. Transações reais desativadas."
    }

@app.get("/api/payments/account")
def get_payment_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _payment_account(db, user.id)
    if not acc:
        return {"configured": False}
    return {
        "configured": True,
        "holder_name": acc.holder_name,
        "pix_key": acc.pix_key,
        "verified": bool(acc.verified)
    }

@app.put("/api/payments/account")
def set_payment_account(data: PaymentAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cpf = only_digits(data.cpf)
    if not valid_cpf(cpf):
        raise HTTPException(422, "CPF inválido")
    if user.cpf_hash and cpf_digest(cpf) != user.cpf_hash:
        raise HTTPException(400, "O CPF da conta de pagamento deve ser o mesmo do cadastro")
    acc = _payment_account(db, user.id)
    if not acc:
        acc = UserPaymentAccount(
            user_id=user.id,
            holder_name=data.holder_name.strip(),
            holder_cpf_hash=cpf_digest(cpf),
            pix_key=data.pix_key.strip(),
            verified=1,
            created_at=now_iso()
        )
        db.add(acc)
    else:
        acc.holder_name=data.holder_name.strip()
        acc.holder_cpf_hash=cpf_digest(cpf)
        acc.pix_key=data.pix_key.strip()
        acc.verified=1
    audit(db,user.id,"PAYMENT_ACCOUNT_UPDATED","pix_key configured")
    db.commit()
    return {"ok":True,"verified":True}

@app.post("/api/payments/pix/charge")
def create_pix_charge(data: PixChargeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payment_mode() != "sandbox":
        raise HTTPException(503, "Modo live não habilitado nesta versão")
    acc=_payment_account(db,user.id)
    if not acc or not acc.verified:
        raise HTTPException(400, "Cadastre e valide sua conta de pagamento primeiro")
    cents=int(round(data.amount*100))
    txid="MX"+secrets.token_hex(12).upper()
    # Payload fictício para teste de UI/fluxo; não envia dinheiro.
    payload=f"000201-MATRIXBET-SANDBOX-TXID-{txid}-AMOUNT-{cents}"
    ch=PixCharge(
        user_id=user.id,txid=txid,amount_cents=cents,status="pending",
        pix_copy_paste=payload,created_at=now_iso()
    )
    db.add(ch); db.flush()
    audit(db,user.id,"PIX_SANDBOX_CREATED",f"txid={txid};cents={cents}")
    db.commit()
    return {"ok":True,"txid":txid,"amount_cents":cents,"pix_copy_paste":payload,"status":"pending"}

@app.post("/api/payments/pix/webhook-sandbox")
def pix_webhook_sandbox(data: PixWebhookSandboxIn, db: Session = Depends(get_db)):
    if payment_mode() != "sandbox":
        raise HTTPException(404, "Webhook sandbox desativado")
    ch=db.scalar(select(PixCharge).where(PixCharge.txid==data.txid))
    if not ch:
        raise HTTPException(404,"Cobrança não encontrada")
    if ch.status!="pending":
        return {"ok":True,"status":ch.status}
    user=db.get(User,ch.user_id)
    payer=only_digits(data.payer_cpf)
    if not valid_cpf(payer) or not user or cpf_digest(payer)!=user.cpf_hash:
        ch.status="failed"
        audit(db,ch.user_id,"PIX_SANDBOX_REJECTED","payer CPF mismatch")
        db.commit()
        raise HTTPException(400,"Pagador não corresponde ao CPF cadastrado")
    if data.status=="paid":
        ch.status="paid"; ch.paid_at=now_iso()
        user.demo_balance_cents += ch.amount_cents
        audit(db,user.id,"PIX_SANDBOX_PAID",f"txid={ch.txid};cents={ch.amount_cents}")
    else:
        ch.status="failed"
        audit(db,user.id,"PIX_SANDBOX_FAILED",f"txid={ch.txid}")
    db.commit()
    return {"ok":True,"status":ch.status,"balance_cents":user.demo_balance_cents}

@app.get("/api/payments/pix/charges")
def my_pix_charges(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows=db.scalars(select(PixCharge).where(PixCharge.user_id==user.id).order_by(PixCharge.id.desc()).limit(100)).all()
    return {"items":[{
        "id":x.id,"txid":x.txid,"amount_cents":x.amount_cents,"status":x.status,
        "created_at":x.created_at,"paid_at":x.paid_at
    } for x in rows]}

# ---------- Wallet ----------
@app.get("/api/wallet")
def wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    txs = db.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.user_id == user.id)
        .order_by(WalletTransaction.id.desc())
        .limit(100)
    ).all()
    return {
        "balance_cents": user.demo_balance_cents,
        "transactions": [{
            "id": t.id, "kind": t.kind, "amount_cents": t.amount_cents,
            "status": t.status, "pix_key": t.pix_key or "",
            "receipt_note": t.receipt_note or "", "admin_note": t.admin_note or "",
            "created_at": t.created_at, "decided_at": t.decided_at
        } for t in txs]
    }

@app.post("/api/wallet/deposit")
def request_deposit(data: DepositRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cents = int(round(data.amount * 100))
    tx = WalletTransaction(
        user_id=user.id, kind="deposit", amount_cents=cents, status="pending",
        receipt_note=data.receipt_note.strip(), created_at=now_iso()
    )
    db.add(tx); db.flush()
    audit(db, user.id, "DEPOSIT_REQUESTED", f"tx={tx.id}; cents={cents}")
    db.commit()
    return {"ok": True, "id": tx.id, "message": "Solicitação de depósito enviada para análise."}

@app.post("/api/wallet/withdraw")
def request_withdrawal(data: WithdrawalRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cents = int(round(data.amount * 100))
    if cents > user.demo_balance_cents:
        raise HTTPException(400, "Saldo insuficiente")
    pending = db.scalars(select(WalletTransaction).where(
        WalletTransaction.user_id == user.id,
        WalletTransaction.kind == "withdrawal",
        WalletTransaction.status == "pending"
    )).all()
    reserved = sum(t.amount_cents for t in pending)
    if cents > user.demo_balance_cents - reserved:
        raise HTTPException(400, "Saldo disponível insuficiente por causa de saque pendente")
    tx = WalletTransaction(
        user_id=user.id, kind="withdrawal", amount_cents=cents, status="pending",
        pix_key=data.pix_key.strip(), created_at=now_iso()
    )
    db.add(tx); db.flush()
    audit(db, user.id, "WITHDRAWAL_REQUESTED", f"tx={tx.id}; cents={cents}")
    db.commit()
    return {"ok": True, "id": tx.id, "message": "Solicitação de saque enviada para análise."}

@app.get("/api/admin/wallet")
def admin_wallet(status: str = "", kind: str = "", admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    q = select(WalletTransaction).order_by(WalletTransaction.id.desc())
    if status: q = q.where(WalletTransaction.status == status)
    if kind: q = q.where(WalletTransaction.kind == kind)
    txs = db.scalars(q.limit(300)).all()
    result=[]
    for t in txs:
        u=db.get(User,t.user_id)
        result.append({
            "id":t.id,"user_id":t.user_id,"user_name":u.name if u else "—",
            "user_email":u.email if u else "—","kind":t.kind,
            "amount_cents":t.amount_cents,"status":t.status,"pix_key":t.pix_key or "",
            "receipt_note":t.receipt_note or "","admin_note":t.admin_note or "",
            "created_at":t.created_at,"decided_at":t.decided_at
        })
    return {"items":result}

@app.post("/api/admin/wallet/{tx_id}/decision")
def admin_wallet_decision(tx_id: int, data: WalletDecisionIn, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    tx=db.get(WalletTransaction,tx_id)
    if not tx: raise HTTPException(404,"Solicitação não encontrada")
    if tx.status != "pending": raise HTTPException(409,"Solicitação já foi analisada")
    user=db.get(User,tx.user_id)
    if not user: raise HTTPException(404,"Usuário não encontrado")
    if data.action == "approve":
        if tx.kind == "deposit":
            user.demo_balance_cents += tx.amount_cents
        elif tx.kind == "withdrawal":
            if user.demo_balance_cents < tx.amount_cents:
                raise HTTPException(400,"Saldo do usuário ficou insuficiente")
            user.demo_balance_cents -= tx.amount_cents
        tx.status="approved"
    else:
        tx.status="rejected"
    tx.admin_note=data.admin_note.strip()
    tx.decided_at=now_iso()
    audit(db, admin.id, "WALLET_DECISION", f"tx={tx.id}; action={data.action}; user={user.id}")
    db.commit()
    return {"ok":True,"status":tx.status,"balance_cents":user.demo_balance_cents}

# ---------- Account & Support ----------

@app.get("/api/account/profile")
def account_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "cpf_masked": ("***.***.***-" + user.cpf_last4[-2:]) if user.cpf_last4 else "—",
        "avatar_data": user.avatar_data or "",
        "created_at": user.created_at,
        "is_blocked": bool(user.is_blocked),
        "demo_balance_cents": user.demo_balance_cents,
    }

@app.put("/api/account/avatar")
def update_avatar(
    data: AvatarIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    value = data.avatar_data.strip()
    if value and not value.startswith("data:image/"):
        raise HTTPException(400, "Formato de imagem inválido")
    if len(value) > 500000:
        raise HTTPException(400, "Imagem muito grande")
    user_db = db.get(User, user.id)
    user_db.avatar_data = value or None
    audit(db, user.id, "AVATAR_UPDATED", "set" if value else "removed")
    db.commit()
    return {"ok": True, "avatar_data": user_db.avatar_data or ""}

@app.delete("/api/account/avatar")
def remove_avatar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_db = db.get(User, user.id)
    user_db.avatar_data = None
    audit(db, user.id, "AVATAR_REMOVED", "")
    db.commit()
    return {"ok": True}

@app.post("/api/account/change-password")
def change_password(
    data: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_db = db.get(User, user.id)
    candidate = hash_password(data.current_password, user_db.salt)
    if not hmac.compare_digest(candidate, user_db.password_hash):
        raise HTTPException(400, "Senha atual incorreta")
    new_salt = secrets.token_hex(16)
    user_db.salt = new_salt
    user_db.password_hash = hash_password(data.new_password, new_salt)
    audit(db, user.id, "PASSWORD_CHANGED", "")
    db.commit()
    return {"ok": True}

@app.post("/api/account/change-email")
def change_email(
    data: ChangeEmailIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_db = db.get(User, user.id)
    candidate = hash_password(data.password, user_db.salt)
    if not hmac.compare_digest(candidate, user_db.password_hash):
        raise HTTPException(400, "Senha incorreta")
    email = data.new_email.lower().strip()
    other = db.scalar(select(User).where(User.email == email))
    if other and other.id != user.id:
        raise HTTPException(409, "E-mail já cadastrado")
    user_db.email = email
    audit(db, user.id, "EMAIL_CHANGED", email)
    db.commit()
    return {"ok": True, "email": email}

@app.post("/api/auth/forgot-password")
def forgot_password(
    data: ResetRequestIn,
    request: Request,
    db: Session = Depends(get_db)
):
    rate_limit(request, "forgot", 6, 60)
    email = data.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        return {"ok": True, "message": "Se o e-mail existir, enviaremos instruções."}

    raw = secrets.token_urlsafe(40)
    token_hash = hash_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.add(PasswordReset(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires.isoformat(),
        used=0,
        created_at=now_iso()
    ))
    db.commit()

    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base}/?reset_token={raw}" if base else f"/?reset_token={raw}"
    sent = send_email(
        user.email,
        "Redefinição de senha - MATRIX BET",
        f"Use este link por até 30 minutos para criar uma nova senha:\n\n{link}\n\nSe você não solicitou, ignore esta mensagem."
    )
    audit(db, user.id, "PASSWORD_RESET_REQUEST", "email_sent=" + str(sent))
    db.commit()
    return {
        "ok": True,
        "message": "Se o e-mail existir, enviaremos instruções.",
        "email_configured": bool(os.getenv("SMTP_HOST"))
    }

@app.post("/api/auth/reset-password")
def reset_password(
    data: ResetConfirmIn,
    db: Session = Depends(get_db)
):
    th = hash_token(data.token)
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == th))
    if not row or row.used:
        raise HTTPException(400, "Link de redefinição inválido ou já utilizado")
    if datetime.fromisoformat(row.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(400, "Link de redefinição expirado")
    user = db.get(User, row.user_id)
    salt = secrets.token_hex(16)
    user.salt = salt
    user.password_hash = hash_password(data.new_password, salt)
    row.used = 1
    audit(db, user.id, "PASSWORD_RESET_DONE", "")
    db.commit()
    return {"ok": True}

@app.post("/api/support/tickets")
def create_ticket(
    data: TicketIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = now_iso()
    t = SupportTicket(
        user_id=user.id,
        subject=data.subject.strip(),
        message=data.message.strip(),
        admin_reply="",
        status="OPEN",
        created_at=now,
        updated_at=now
    )
    db.add(t)
    db.flush()
    audit(db, user.id, "SUPPORT_TICKET_OPENED", f"id={t.id}")
    db.commit()
    return {"ok": True, "ticket_id": t.id}

@app.get("/api/support/tickets")
def my_tickets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(SupportTicket)
        .where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.id.desc())
        .limit(100)
    ).all()
    return {"tickets": [{
        "id":t.id,"subject":t.subject,"message":t.message,"admin_reply":t.admin_reply,
        "status":t.status,"created_at":t.created_at,"updated_at":t.updated_at
    } for t in rows]}

# ---------- Admin ----------

@app.get("/api/admin/setup-status")
def admin_setup_status(db: Session = Depends(get_db)):
    from sqlalchemy import func
    count = db.scalar(select(func.count(User.id)).where(User.is_admin == 1)) or 0
    return {"setup_available": count == 0, "admin_count": int(count)}

@app.post("/api/admin/setup")
def admin_setup(data: AdminSetupIn, db: Session = Depends(get_db)):
    from sqlalchemy import func
    count = db.scalar(select(func.count(User.id)).where(User.is_admin == 1)) or 0
    if count > 0:
        raise HTTPException(403, "O administrador inicial já foi cadastrado")

    email = data.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(409, "Este e-mail já está em uso")

    # Admin does not need CPF for account administration.
    salt_hex = secrets.token_hex(16)
    admin_user = User(
        name=data.name.strip(),
        email=email,
        cpf_hash="ADMIN-" + secrets.token_hex(16),
        cpf_last4="",
        password_hash=hash_password(data.password, salt_hex),
        salt=salt_hex,
        is_admin=1,
        is_blocked=0,
        demo_balance_cents=0,
        created_at=now_iso(),
    )
    try:
        db.add(admin_user)
        db.flush()
        audit(db, admin_user.id, "ADMIN_INITIAL_SETUP", "Primeiro administrador criado")
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Não foi possível criar o administrador")
    return {"ok": True, "message": "Administrador criado. Agora faça o login."}

@app.post("/api/admin/login")
def admin_login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "admin-login", 8, 60)
    email = data.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_admin:
        raise HTTPException(401, "Credenciais administrativas inválidas")
    candidate = hash_password(data.password, user.salt)
    if not hmac.compare_digest(candidate, user.password_hash):
        raise HTTPException(401, "Credenciais administrativas inválidas")
    token = create_session(db, user.id)
    audit(db, user.id, "ADMIN_LOGIN", "")
    db.commit()
    return {"token": token, "user": {"id":user.id,"name":user.name,"email":user.email}}

@app.get("/api/admin/stats")
def admin_stats(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    from sqlalchemy import func
    users_count = db.scalar(select(func.count(User.id)).where(User.is_admin == 0)) or 0
    blocked_count = db.scalar(select(func.count(User.id)).where(User.is_blocked == 1, User.is_admin == 0)) or 0
    bets_count = db.scalar(select(func.count(Bet.id))) or 0
    open_bets = db.scalar(select(func.count(Bet.id)).where(Bet.status == "OPEN")) or 0
    open_tickets = db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.status != "RESOLVED")) or 0
    stake_total = db.scalar(select(func.coalesce(func.sum(Bet.stake_cents), 0))) or 0
    return {"users": users_count, "blocked_users": blocked_count, "bets": bets_count,
            "open_bets": open_bets, "open_tickets": open_tickets, "stake_total_cents": int(stake_total),
            "database": "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite",
            "persistent_database": DATABASE_URL.startswith("postgresql")}

@app.get("/api/admin/users")
def admin_users(q: str = "", blocked: str = "all", admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    stmt = select(User).where(User.is_admin == 0)
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where((User.name.ilike(like)) | (User.email.ilike(like)))
    if blocked == "yes":
        stmt = stmt.where(User.is_blocked == 1)
    elif blocked == "no":
        stmt = stmt.where(User.is_blocked == 0)
    rows = db.scalars(stmt.order_by(User.id.desc()).limit(500)).all()
    return {"users": [{"id":u.id,"name":u.name,"email":u.email,
        "cpf_masked": ("***.***.***-" + u.cpf_last4[-2:]) if u.cpf_last4 else "—",
        "is_blocked": bool(u.is_blocked),"demo_balance_cents":u.demo_balance_cents,
        "created_at":u.created_at} for u in rows]}

@app.get("/api/admin/users/{user_id}/details")
def admin_user_details(user_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.is_admin:
        raise HTTPException(404, "Usuário não encontrado")
    bets = db.scalars(select(Bet).where(Bet.user_id == user_id).order_by(Bet.id.desc()).limit(100)).all()
    tickets = db.scalars(select(SupportTicket).where(SupportTicket.user_id == user_id).order_by(SupportTicket.id.desc()).limit(100)).all()
    activity = db.scalars(select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.id.desc()).limit(150)).all()
    return {"user":{"id":u.id,"name":u.name,"email":u.email,
            "cpf_masked": ("***.***.***-" + u.cpf_last4[-2:]) if u.cpf_last4 else "—",
            "is_blocked":bool(u.is_blocked),"demo_balance_cents":u.demo_balance_cents,"created_at":u.created_at},
        "bets":[{"id":b.id,"stake_cents":b.stake_cents,"total_odd":b.total_odd,
                 "potential_return_cents":b.potential_return_cents,"status":b.status,"created_at":b.created_at} for b in bets],
        "tickets":[{"id":t.id,"subject":t.subject,"status":t.status,"created_at":t.created_at,"updated_at":t.updated_at} for t in tickets],
        "activity":[{"id":a.id,"action":a.action,"details":a.details,"created_at":a.created_at} for a in activity]}

@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, data: UserAdminUpdateIn, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.is_admin: raise HTTPException(404, "Usuário não encontrado")
    u.is_blocked = 1 if data.is_blocked else 0
    audit(db, admin.id, "ADMIN_USER_BLOCK_CHANGE", f"user={user_id};blocked={data.is_blocked}")
    db.commit()
    return {"ok": True}

@app.patch("/api/admin/users/{user_id}/demo-balance")
def admin_update_demo_balance(user_id: int, data: UserBalanceAdminIn, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.is_admin: raise HTTPException(404, "Usuário não encontrado")
    old = u.demo_balance_cents
    u.demo_balance_cents = data.demo_balance_cents
    audit(db, admin.id, "ADMIN_DEMO_BALANCE_CHANGE", f"user={user_id};old={old};new={data.demo_balance_cents}")
    db.commit()
    return {"ok": True, "demo_balance_cents": u.demo_balance_cents}

@app.get("/api/admin/bets")
def admin_bets(q: str = "", status: str = "all", admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    stmt = select(Bet, User).join(User, User.id == Bet.user_id)
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where((User.name.ilike(like)) | (User.email.ilike(like)))
    if status != "all":
        stmt = stmt.where(Bet.status == status.upper())
    rows = db.execute(stmt.order_by(Bet.id.desc()).limit(500)).all()
    return {"bets": [{"id":b.id,"user_id":u.id,"username":u.name,"email":u.email,
        "stake_cents":b.stake_cents,"total_odd":b.total_odd,"potential_return_cents":b.potential_return_cents,
        "status":b.status,"created_at":b.created_at} for b,u in rows]}

@app.get("/api/admin/activity")
def admin_activity(q: str = "", admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    q = q.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where((AuditLog.action.ilike(like)) | (AuditLog.details.ilike(like)))
    rows = db.scalars(stmt.limit(500)).all()
    user_ids = {a.user_id for a in rows if a.user_id}
    users = {}
    if user_ids:
        for u in db.scalars(select(User).where(User.id.in_(user_ids))).all():
            users[u.id] = u
    return {"activity": [{"id":a.id,"user_id":a.user_id,
        "username":users[a.user_id].name if a.user_id in users else "Sistema",
        "action":a.action,"details":a.details,"created_at":a.created_at} for a in rows]}

@app.get("/api/admin/support")
def admin_support(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(SupportTicket, User)
        .join(User, User.id == SupportTicket.user_id)
        .order_by(SupportTicket.id.desc())
        .limit(500)
    ).all()
    return {"tickets": [{
        "id":t.id,"user_id":u.id,"username":u.name,"email":u.email,
        "subject":t.subject,"message":t.message,"admin_reply":t.admin_reply,
        "status":t.status,"created_at":t.created_at,"updated_at":t.updated_at
    } for t,u in rows]}

@app.patch("/api/admin/support/{ticket_id}")
def admin_reply_ticket(
    ticket_id: int,
    data: TicketReplyIn,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    t = db.get(SupportTicket, ticket_id)
    if not t:
        raise HTTPException(404, "Chamado não encontrado")
    status = data.status.upper()
    if status not in {"OPEN","IN_PROGRESS","RESOLVED"}:
        raise HTTPException(400, "Status inválido")
    t.admin_reply = data.reply.strip()
    t.status = status
    t.updated_at = now_iso()
    audit(db, admin.id, "SUPPORT_TICKET_REPLY", f"ticket={ticket_id};status={status}")
    db.commit()
    return {"ok": True}



CASINO_DEMO_CATEGORIES = [
    {"id":"slots","name":"Slots","icon":"🎰"},
    {"id":"live","name":"Cassino ao Vivo","icon":"🎥"},
    {"id":"roulette","name":"Roleta","icon":"🎡"},
    {"id":"blackjack","name":"Blackjack","icon":"🃏"},
    {"id":"crash","name":"Crash","icon":"🚀"},
]

@app.get("/api/casino/catalog")
def casino_catalog(user: User = Depends(get_current_user)):
    return {
        "mode":"provider-ready",
        "connected":False,
        "categories":CASINO_DEMO_CATEGORIES,
        "message":"Aguardando credenciais do agregador B2B."
    }


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

@app.get("/admin-service-worker.js")
def admin_service_worker():
    response = FileResponse(
        FRONTEND / "admin-service-worker.js",
        media_type="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.get("/api/app-mode")
def app_mode():
    return {
        "mode": os.getenv("APP_MODE", "user").strip().lower(),
        "version": "6.8.0",
        "hostname": os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
    }

@app.get("/usuario")
def usuario_app():
    return FileResponse(FRONTEND / "index.html")

@app.get("/admin")
@app.get("/admin/")
@app.get("/painel-adm")
@app.get("/painel-adm/")
@app.get("/admin-login")
def admin_page():
    # Endereço fixo do administrador.
    # Redireciona para o arquivo administrativo que já foi validado no navegador.
    return RedirectResponse(url="/static/admin.html", status_code=307)

@app.get("/api/admin/status")
def admin_status(admin: User = Depends(get_admin_user)):
    return {
        "ok": True,
        "version": "6.8.0",
        "admin": {"id": admin.id, "name": admin.name, "email": admin.email}
    }

@app.get("/")
def home():
    mode = os.getenv("APP_MODE", "user").strip().lower()
    if mode == "admin":
        return RedirectResponse(url="/static/admin.html", status_code=307)
    return FileResponse(FRONTEND / "index.html")
