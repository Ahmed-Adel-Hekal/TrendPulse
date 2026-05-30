"""db.py — Database connection, init, and all CRUD helpers. (v4 — improved)"""
from __future__ import annotations
import json, os, sqlite3, uuid, datetime, threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH     = Path(os.getenv("DATABASE_PATH", "data/saas.db"))
OUTPUT_ROOT = Path("outputs")
PLAN_QUOTAS = {"free": 10, "starter": 50, "pro": 200, "agency": 1000}
PLAN_PRICES = {"free": "$0", "starter": "$19", "pro": "$49", "agency": "$149"}
PLATFORM_CHOICES = ["Instagram", "TikTok", "LinkedIn", "Twitter/X", "Facebook"]
LANGUAGE_CHOICES = ["English", "Arabic", "Egyptian Arabic", "Gulf Arabic",
                    "French", "Spanish", "German"]

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

import logging
logger = logging.getLogger("TrendPulse.db")

# ── Thread-local connection cache ──────────────────────────────────────────────
_local = threading.local()


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-16000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=134217728")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def get_conn():
    """Thread-local connection with automatic commit/rollback."""
    if not getattr(_local, "conn", None):
        _local.conn = _make_conn()
    conn = _local.conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Helpers ────────────────────────────────────────────────────────────────────
def now_iso():       return datetime.datetime.utcnow().isoformat()
def current_month(): return datetime.datetime.utcnow().strftime("%Y-%m")

def safe_json_loads(raw, default=None):
    if not raw: return default
    if isinstance(raw, (dict, list)): return raw
    try:    return json.loads(raw)
    except: return default

def safe_json_dumps(obj):
    try:    return json.dumps(obj, ensure_ascii=False)
    except: return "{}"


# ── Schema ─────────────────────────────────────────────────────────────────────
def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            is_active INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS generations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            content_type TEXT NOT NULL,
            platforms TEXT NOT NULL,
            language TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result_json TEXT,
            error TEXT,
            config_json TEXT,
            fallback_used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            scheduled_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS usage (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            gen_id TEXT NOT NULL,
            month TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS brands (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}',
            is_default INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            brand_id TEXT,
            title TEXT NOT NULL,
            topic TEXT NOT NULL,
            duration_days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'draft',
            plan_json TEXT,
            created_at TEXT NOT NULL,
            approved_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS calendar_items (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            strategy_id TEXT,
            generation_id TEXT,
            brand_id TEXT,
            title TEXT NOT NULL,
            platform TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'static',
            publish_date TEXT NOT NULL,
            publish_time TEXT DEFAULT '09:00',
            status TEXT DEFAULT 'scheduled',
            notes TEXT,
            idea_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            gemini_key TEXT NOT NULL DEFAULT '',
            openrouter_key TEXT NOT NULL DEFAULT '',
            aiml_key TEXT NOT NULL DEFAULT '',
            llm_provider TEXT NOT NULL DEFAULT 'google',
            llm_model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
            image_model TEXT NOT NULL DEFAULT 'gemini-3.1-flash-image-preview',
            video_model TEXT NOT NULL DEFAULT 'google/veo-3.1-i2v',
            ui_language TEXT NOT NULL DEFAULT 'en',
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS admin_logs (
            id TEXT PRIMARY KEY,
            admin_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gen_user          ON generations(user_id);
        CREATE INDEX IF NOT EXISTS idx_gen_status_sched  ON generations(status, scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_gen_status        ON generations(status);
        CREATE INDEX IF NOT EXISTS idx_usage_user        ON usage(user_id, month);
        CREATE INDEX IF NOT EXISTS idx_brands_user       ON brands(user_id);
        CREATE INDEX IF NOT EXISTS idx_strat_user        ON strategies(user_id);
        CREATE INDEX IF NOT EXISTS idx_cal_user          ON calendar_items(user_id, publish_date);
        CREATE INDEX IF NOT EXISTS idx_settings_user     ON user_settings(user_id);
        CREATE INDEX IF NOT EXISTS idx_admin_logs        ON admin_logs(admin_id, created_at);
        """)

    # Incremental migrations — safe to run multiple times
    migrations = [
        "ALTER TABLE users ADD COLUMN brand_profile TEXT DEFAULT '{}'",
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ban_reason TEXT",
        "ALTER TABLE generations ADD COLUMN scheduled_at TEXT",
        "ALTER TABLE generations ADD COLUMN fallback_used INTEGER DEFAULT 0",
        "ALTER TABLE calendar_items ADD COLUMN publish_time TEXT DEFAULT '09:00'",
        "ALTER TABLE user_settings ADD COLUMN ui_language TEXT NOT NULL DEFAULT 'en'",
    ]
    for m in migrations:
        with get_conn() as conn:
            try: conn.execute(m)
            except Exception: pass

    # Ensure index exists (may not exist on old DBs)
    with get_conn() as conn:
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gen_status_sched ON generations(status, scheduled_at)")
        except Exception:
            pass

    logger.info("Database ready: %s", DB_PATH)


# ── User CRUD ──────────────────────────────────────────────────────────────────
def get_user_by_email(email):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email=? AND is_active=1 AND (is_banned=0 OR is_banned IS NULL)",
            (email.lower().strip(),)
        ).fetchone()
    return dict(row) if row else None

def get_user_by_id(uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None

def create_user(email, name, password, is_admin=False):
    """
    Create a new user AND initialize their user_settings row atomically.
    FIX: Previously the settings row was never created, causing KeyError /
    NoneType errors on first login and throughout the app.
    """
    from auth import hash_password
    uid = str(uuid.uuid4())
    ts  = now_iso()
    with get_conn() as conn:
        # Insert the user
        conn.execute(
            "INSERT INTO users (id,email,name,password_hash,is_admin,created_at) VALUES (?,?,?,?,?,?)",
            (uid, email.lower().strip(), name.strip(), hash_password(password),
             1 if is_admin else 0, ts)
        )
        # ── FIX: always create a settings row so downstream code never gets None ──
        conn.execute(
            """INSERT OR IGNORE INTO user_settings
               (user_id, gemini_key, openrouter_key, aiml_key,
                llm_provider, llm_model, image_model, video_model,
                ui_language, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (uid, '', '', '', 'google', 'gemini-2.5-flash',
             'gemini-3.1-flash-image-preview', 'google/veo-3.1-i2v', 'en', ts)
        )
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row)

def update_last_login(uid):
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), uid))

def get_all_users(limit=500, search="", plan_filter="", status_filter=""):
    query = "SELECT * FROM users WHERE 1=1"
    params = []
    if search:
        query += " AND (name LIKE ? OR email LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if plan_filter:
        query += " AND plan=?"
        params.append(plan_filter)
    if status_filter == "banned":
        query += " AND is_banned=1"
    elif status_filter == "active":
        query += " AND is_banned=0 AND is_active=1"
    elif status_filter == "admin":
        query += " AND is_admin=1"
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def update_user_plan(uid, plan):
    with get_conn() as conn:
        conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))

def set_user_admin(uid, is_admin: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin=? WHERE id=?", (1 if is_admin else 0, uid))

def ban_user(uid, reason=""):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE id=?", (reason, uid))

def unban_user(uid):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE id=?", (uid,))

def delete_user_admin(uid):
    """Hard delete a user and all their data (admin only)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM usage          WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM generations    WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM brands         WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM strategies     WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM calendar_items WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM user_settings  WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM users          WHERE id=?",      (uid,))

def get_brand_profile(uid):
    with get_conn() as conn:
        row = conn.execute("SELECT brand_profile FROM users WHERE id=?", (uid,)).fetchone()
    if not row: return {}
    return safe_json_loads(row["brand_profile"], {})

def save_brand_profile(uid, profile):
    with get_conn() as conn:
        conn.execute("UPDATE users SET brand_profile=? WHERE id=?",
                     (json.dumps(profile, ensure_ascii=False), uid))


# ── User Settings ──────────────────────────────────────────────────────────────
_SETTINGS_DEFAULTS = {
    "gemini_key": "", "openrouter_key": "", "aiml_key": "",
    "llm_provider": "google", "llm_model": "gemini-2.5-flash",
    "image_model": "gemini-3.1-flash-image-preview",
    "video_model": "google/veo-3.1-i2v",
    "ui_language": "en",
}

def get_user_settings(uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_settings WHERE user_id=?", (uid,)).fetchone()
    if row:
        d = dict(row)
        if "ui_language" not in d or not d["ui_language"]:
            d["ui_language"] = "en"
        return d
    # ── FIX: return defaults instead of an empty dict to prevent KeyError ──
    return dict(_SETTINGS_DEFAULTS)

def save_user_settings(uid, s):
    with get_conn() as conn:
        conn.execute("""INSERT INTO user_settings
               (user_id,gemini_key,openrouter_key,aiml_key,
                llm_provider,llm_model,image_model,video_model,ui_language,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
               gemini_key=excluded.gemini_key,
               openrouter_key=excluded.openrouter_key,
               aiml_key=excluded.aiml_key,
               llm_provider=excluded.llm_provider,
               llm_model=excluded.llm_model,
               image_model=excluded.image_model,
               video_model=excluded.video_model,
               ui_language=excluded.ui_language,
               updated_at=excluded.updated_at""",
            (uid, s.get("gemini_key",""), s.get("openrouter_key",""),
             s.get("aiml_key",""), s.get("llm_provider","google"),
             s.get("llm_model","gemini-2.5-flash"),
             s.get("image_model","gemini-3.1-flash-image-preview"),
             s.get("video_model","google/veo-3.1-i2v"),
             s.get("ui_language","en"), now_iso()))

def get_user_ui_language(uid: str) -> str:
    """Fast single-column read for middleware use."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT ui_language FROM user_settings WHERE user_id=?", (uid,)
        ).fetchone()
    if row and row["ui_language"]:
        return row["ui_language"]
    return "en"

def set_user_ui_language(uid: str, lang: str):
    with get_conn() as conn:
        conn.execute("""INSERT INTO user_settings (user_id, ui_language, updated_at)
            VALUES (?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET ui_language=excluded.ui_language, updated_at=excluded.updated_at""",
            (uid, lang, now_iso()))


# ── Brand CRUD ─────────────────────────────────────────────────────────────────
def _parse_brand(row):
    d = dict(row)
    d["profile"] = safe_json_loads(d.get("profile_json"), {})
    return d

def get_brands(uid):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM brands WHERE user_id=? ORDER BY is_default DESC, created_at ASC",
            (uid,)
        ).fetchall()
    return [_parse_brand(r) for r in rows]

def get_brand(brand_id, uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM brands WHERE id=? AND user_id=?",
                           (brand_id, uid)).fetchone()
    return _parse_brand(row) if row else None

def get_default_brand(uid):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM brands WHERE user_id=? AND is_default=1 LIMIT 1", (uid,)
        ).fetchone()
    if not row:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM brands WHERE user_id=? ORDER BY created_at ASC LIMIT 1", (uid,)
            ).fetchone()
    return _parse_brand(row) if row else None

def create_brand(uid, name, profile):
    bid = str(uuid.uuid4())
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM brands WHERE user_id=?", (uid,)).fetchone()[0]
        conn.execute(
            "INSERT INTO brands (id,user_id,name,profile_json,is_default,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (bid, uid, name, json.dumps(profile, ensure_ascii=False),
             1 if count == 0 else 0, now_iso(), now_iso())
        )
    return bid

def update_brand(brand_id, uid, name, profile):
    with get_conn() as conn:
        conn.execute(
            "UPDATE brands SET name=?,profile_json=?,updated_at=? WHERE id=? AND user_id=?",
            (name, json.dumps(profile, ensure_ascii=False), now_iso(), brand_id, uid)
        )

def delete_brand(brand_id, uid):
    with get_conn() as conn:
        conn.execute("DELETE FROM brands WHERE id=? AND user_id=?", (brand_id, uid))

def set_default_brand(brand_id, uid):
    with get_conn() as conn:
        conn.execute("UPDATE brands SET is_default=0 WHERE user_id=?", (uid,))
        conn.execute("UPDATE brands SET is_default=1 WHERE id=? AND user_id=?", (brand_id, uid))


# ── Strategy CRUD ──────────────────────────────────────────────────────────────
def create_strategy(uid, brand_id, title, topic, duration_days=30):
    sid = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO strategies (id,user_id,brand_id,title,topic,duration_days,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (sid, uid, brand_id, title, topic, duration_days, "generating", now_iso())
        )
    return sid

def update_strategy(sid, status, plan=None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE strategies SET status=?,plan_json=?,approved_at=? WHERE id=?",
            (status, json.dumps(plan) if plan else None,
             now_iso() if status == "approved" else None, sid)
        )

def get_strategy(sid, uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE id=? AND user_id=?", (sid, uid)).fetchone()
    if not row: return None
    d = dict(row)
    if d.get("plan_json"):
        d["plan"] = safe_json_loads(d["plan_json"], {})
    return d

def get_user_strategies(uid, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("plan_json"):
            d["plan"] = safe_json_loads(d["plan_json"], {})
        out.append(d)
    return out


# ── Calendar CRUD ──────────────────────────────────────────────────────────────
def add_calendar_items(uid, items):
    if not items: return []
    ids  = [str(uuid.uuid4()) for _ in items]
    ts   = now_iso()
    rows = [
        (ids[i], uid, item.get("strategy_id"), item.get("generation_id"),
         item.get("brand_id"), item.get("title",""), item.get("platform",""),
         item.get("content_type","static"), item.get("publish_date",""),
         item.get("publish_time","09:00"), item.get("status","scheduled"),
         item.get("notes",""), json.dumps(item.get("idea",{})), ts)
        for i, item in enumerate(items)
    ]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO calendar_items "
            "(id,user_id,strategy_id,generation_id,brand_id,title,platform,"
            "content_type,publish_date,publish_time,status,notes,idea_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    return ids

def get_calendar_item(cid, uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM calendar_items WHERE id=? AND user_id=?",
                           (cid, uid)).fetchone()
    if not row: return None
    d = dict(row)
    d["idea"] = safe_json_loads(d.get("idea_json"), {})
    return d

def get_calendar_items(uid, year, month):
    prefix = f"{year}-{month:02d}"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM calendar_items WHERE user_id=? AND publish_date LIKE ? ORDER BY publish_date ASC",
            (uid, f"{prefix}%")
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["idea"] = safe_json_loads(d.get("idea_json"), {})
        out.append(d)
    return out

def update_calendar_item_status(cid, uid, status):
    with get_conn() as conn:
        conn.execute("UPDATE calendar_items SET status=? WHERE id=? AND user_id=?",
                     (status, cid, uid))

def delete_calendar_item(cid, uid):
    with get_conn() as conn:
        conn.execute("DELETE FROM calendar_items WHERE id=? AND user_id=?", (cid, uid))


# ── Quota & Usage — ATOMIC ─────────────────────────────────────────────────────
def get_usage_this_month(uid):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM usage WHERE user_id=? AND month=?",
            (uid, current_month())
        ).fetchone()
    return row["cnt"] if row else 0

def record_usage(uid, gid):
    """Record usage ONLY on successful completion (called from update_generation on success)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO usage (id,user_id,gen_id,month,created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), uid, gid, current_month(), now_iso())
        )

def quota_ok_atomic(user) -> bool:
    uid   = user["id"]
    plan  = user.get("plan", "free")
    limit = PLAN_QUOTAS.get(plan, 10)
    month = current_month()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM usage WHERE user_id=? AND month=?",
            (uid, month)
        ).fetchone()
        used = row["cnt"] if row else 0
        return used < limit

def quota_ok(user) -> bool:
    return get_usage_this_month(user["id"]) < PLAN_QUOTAS.get(user.get("plan","free"), 10)

def quota_status(user):
    plan  = user.get("plan", "free")
    limit = PLAN_QUOTAS.get(plan, 10)
    used  = get_usage_this_month(user["id"])
    return {"used": used, "limit": limit, "plan": plan, "remaining": max(0, limit - used)}


# ── Generation CRUD ────────────────────────────────────────────────────────────
NICHE_KW = {
    "tech":    ["ai","ml","llm","software","dev","code","saas","cloud"],
    "fashion": ["fashion","beauty","style","makeup","skincare"],
    "fitness": ["fitness","workout","gym","sport","nutrition"],
    "food":    ["food","recipe","meal","cook","restaurant","chef"],
    "finance": ["finance","invest","crypto","stock","money","fintech"],
    "health":  ["health","medical","wellness","doctor","pharma"],
}

def detect_niche(topic):
    t = topic.lower()
    for niche, kws in NICHE_KW.items():
        if any(k in t for k in kws): return niche
    return "marketing"

def _sanitise_for_json(obj):
    from dataclasses import asdict, is_dataclass
    if is_dataclass(obj) and not isinstance(obj, type):
        return _sanitise_for_json(asdict(obj))
    if isinstance(obj, dict):
        return {k: _sanitise_for_json(v) for k, v in obj.items() if k != "raw_ranked"}
    if isinstance(obj, (list, tuple)):
        return [_sanitise_for_json(i) for i in obj]
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    try:
        import numpy as _np
        if isinstance(obj, _np.integer):  return int(obj)
        if isinstance(obj, _np.floating): return float(obj)
        if isinstance(obj, _np.bool_):    return bool(obj)
        if isinstance(obj, _np.ndarray):  return obj.tolist()
    except ImportError:
        pass
    if not isinstance(obj, (str, int, float, bool, type(None))):
        try:    json.dumps(obj)
        except: return str(obj)
    return obj

def create_generation(uid, topic, content_type, platforms, language, config=None):
    gid = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO generations (id,user_id,topic,content_type,platforms,language,status,config_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (gid, uid, topic, content_type, json.dumps(platforms), language,
             "pending", json.dumps(config or {}), now_iso())
        )
    return gid

def create_scheduled_generation(uid, topic, content_type, platforms, language,
                                 scheduled_at, cfg=None):
    gid = str(uuid.uuid4())
    cfg = dict(cfg or {})
    cfg["scheduled_at"] = scheduled_at
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO generations "
            "(id,user_id,topic,content_type,platforms,language,status,config_json,scheduled_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (gid, uid, topic, content_type, json.dumps(platforms), language,
             "scheduled", json.dumps(cfg, ensure_ascii=False), scheduled_at, now_iso())
        )
    return gid

def update_generation(gid, status, result=None, error=None, fallback_used=False):
    if result is not None:
        try:
            result = _sanitise_for_json(result)
            json.dumps(result)
        except Exception as e:
            logger.warning("update_generation: not serialisable: %s", e)
            error = error or str(e); result = None; status = "failed"

    # Record usage ONLY on successful completion
    if status == "completed" and result is not None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT user_id FROM generations WHERE id=?", (gid,)
            ).fetchone()
        if row:
            try:
                record_usage(row["user_id"], gid)
            except Exception as e:
                logger.warning("record_usage failed for %s: %s", gid, e)

    with get_conn() as conn:
        conn.execute(
            "UPDATE generations SET status=?,result_json=?,error=?,completed_at=?,fallback_used=? WHERE id=?",
            (status,
             json.dumps(result) if result else None,
             error,
             now_iso() if status in ("completed","failed","awaiting_approval") else None,
             1 if fallback_used else 0,
             gid)
        )

def get_generation(gid, uid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM generations WHERE id=? AND user_id=?",
                           (gid, uid)).fetchone()
    if not row: return None
    d = dict(row)
    d["platforms"] = safe_json_loads(d.get("platforms"), [])
    d["config"]    = safe_json_loads(d.get("config_json"), {})
    if d.get("result_json"):
        d["result"] = safe_json_loads(d["result_json"], {})
    return d

def get_generation_admin(gid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM generations WHERE id=?", (gid,)).fetchone()
    if not row: return None
    d = dict(row)
    d["platforms"] = safe_json_loads(d.get("platforms"), [])
    d["config"]    = safe_json_loads(d.get("config_json"), {})
    if d.get("result_json"):
        d["result"] = safe_json_loads(d["result_json"], {})
    return d

def get_user_generations(uid, limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,topic,content_type,platforms,language,status,created_at,completed_at,scheduled_at,fallback_used "
            "FROM generations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["platforms"] = safe_json_loads(d.get("platforms"), [])
        out.append(d)
    return out

def get_all_generations_admin(limit=200, status_filter="", user_id=""):
    q = "SELECT g.*, u.email as user_email, u.name as user_name FROM generations g LEFT JOIN users u ON g.user_id=u.id WHERE 1=1"
    params = []
    if status_filter:
        q += " AND g.status=?"; params.append(status_filter)
    if user_id:
        q += " AND g.user_id=?"; params.append(user_id)
    q += " ORDER BY g.created_at DESC LIMIT ?"; params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["platforms"] = safe_json_loads(d.get("platforms"), [])
        out.append(d)
    return out

def cancel_scheduled_generation(gid, uid):
    with get_conn() as conn:
        conn.execute(
            "UPDATE generations SET status='cancelled' "
            "WHERE id=? AND user_id=? AND status='scheduled'", (gid, uid)
        )

def get_scheduled_generations(uid, strategy_id=None):
    with get_conn() as conn:
        if strategy_id:
            rows = conn.execute(
                "SELECT * FROM generations WHERE user_id=? AND status='scheduled' "
                "AND json_extract(config_json,'$.strategy_id')=? ORDER BY scheduled_at ASC",
                (uid, strategy_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM generations WHERE user_id=? AND status='scheduled' "
                "ORDER BY scheduled_at ASC", (uid,)
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["config"] = safe_json_loads(d.get("config_json"), {})
        out.append(d)
    return out


# ── Admin Logs ─────────────────────────────────────────────────────────────────
def log_admin_action(admin_id, action, target_type="", target_id="", details=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admin_logs (id,admin_id,action,target_type,target_id,details,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), admin_id, action, target_type, target_id, details, now_iso())
        )

def get_admin_logs(limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT l.*, u.email as admin_email FROM admin_logs l "
            "LEFT JOIN users u ON l.admin_id=u.id "
            "ORDER BY l.created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── System Stats ───────────────────────────────────────────────────────────────
def get_system_stats():
    with get_conn() as conn:
        total_users   = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        total_gens    = conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
        month_gens    = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE month=?", (current_month(),)
        ).fetchone()[0]
        by_status     = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM generations GROUP BY status"
        ).fetchall()
        by_plan       = conn.execute(
            "SELECT plan, COUNT(*) as cnt FROM users WHERE is_active=1 GROUP BY plan"
        ).fetchall()
        total_brands  = conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
        total_strats  = conn.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
        banned_users  = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_banned=1"
        ).fetchone()[0]
        admin_users   = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin=1"
        ).fetchone()[0]
        recent_signups= conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now','-7 days')"
        ).fetchone()[0]
        fallback_gens = conn.execute(
            "SELECT COUNT(*) FROM generations WHERE fallback_used=1"
        ).fetchone()[0]

    return {
        "total_users":    total_users,
        "total_gens":     total_gens,
        "month_gens":     month_gens,
        "by_status":      {r["status"]: r["cnt"] for r in by_status},
        "by_plan":        {r["plan"]: r["cnt"] for r in by_plan},
        "total_brands":   total_brands,
        "total_strats":   total_strats,
        "banned_users":   banned_users,
        "admin_users":    admin_users,
        "recent_signups": recent_signups,
        "fallback_gens":  fallback_gens,
    }


# ── System Settings ────────────────────────────────────────────────────────────
def get_system_setting(key, default=""):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_system_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO system_settings (key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_iso())
        )

def get_all_system_settings():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM system_settings ORDER BY key").fetchall()
    return [dict(r) for r in rows]



def quota_ok_atomic(user) -> bool:
    """
    Atomically claim one quota slot for this user in the current month.

    Returns True  — slot reserved, generation may proceed.
    Returns False — quota exhausted, caller must reject.

    Inserts a placeholder usage row with gen_id='__reserved__'.
    The caller MUST later call either:
      - record_usage(uid, real_gid)        on success
      - release_quota_reservation(uid)     on failure/cancel
    """
    uid   = user["id"]
    plan  = user.get("plan", "free")
    limit = PLAN_QUOTAS.get(plan, 10)
    month = current_month()

    with get_conn() as conn:
        used = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE user_id=? AND month=?",
            (uid, month)
        ).fetchone()[0]

        if used >= limit:
            return False

        try:
            conn.execute(
                "INSERT INTO usage (id, user_id, gen_id, month, created_at) "
                "VALUES (?, ?, '__reserved__', ?, ?)",
                (str(_uuid.uuid4()), uid, month, now_iso())
            )
            return True
        except Exception:
            # Concurrent write filled the last slot between our COUNT and INSERT
            return False


def release_quota_reservation(uid: str):
    """
    Return a reserved slot to the pool.

    Call this when a generation fails or is cancelled BEFORE it completes,
    so the user's quota is not consumed for work that never finished.

    Deletes the oldest '__reserved__' row for this user this month.
    Safe to call even if no reservation exists (no-op).
    """
    month = current_month()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM usage "
            "WHERE user_id=? AND month=? AND gen_id='__reserved__' "
            "ORDER BY created_at ASC LIMIT 1",
            (uid, month)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM usage WHERE id=?", (row["id"],))


def record_usage(uid: str, gid: str):
    """
    Confirm a quota slot was used for a completed generation.

    Upgrades the oldest '__reserved__' placeholder row to the real gen_id.
    Falls back to inserting a fresh row if no placeholder exists
    (handles the legacy path where quota_ok_atomic wasn't used).

    Called by update_generation() when status → 'completed'.
    """
    month = current_month()
    with get_conn() as conn:
        # Try to upgrade an existing reservation
        conn.execute(
            "UPDATE usage SET gen_id=? "
            "WHERE id = ("
            "  SELECT id FROM usage "
            "  WHERE user_id=? AND month=? AND gen_id='__reserved__' "
            "  ORDER BY created_at ASC LIMIT 1"
            ")",
            (gid, uid, month)
        )
        # If nothing upgraded (no reservation), insert a fresh confirmed row
        already = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE user_id=? AND gen_id=?",
            (uid, gid)
        ).fetchone()[0]
        if not already:
            conn.execute(
                "INSERT INTO usage (id, user_id, gen_id, month, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(_uuid.uuid4()), uid, gid, month, now_iso())
            )
