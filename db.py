import psycopg2
import psycopg2.extras

DEFAULT_DB_CONFIG = {
    'mode': 'localhost',
    'host': 'localhost',
    'port': 5432,
    'database': 'postgres',
    'user': 'postgres',
    'password': '',
    'auto_save': False,
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transcripts (
    id          SERIAL PRIMARY KEY,
    text        TEXT NOT NULL,
    engine      VARCHAR(64),
    language    VARCHAR(16),
    source      VARCHAR(16),
    filename    VARCHAR(255),
    confidence  REAL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _ensure_schema(cur):
    # CREATE TABLE IF NOT EXISTS still requires CREATE on the schema even when the table
    # exists, so check first to let read/write-only users work once the table is created.
    cur.execute("SELECT to_regclass('transcripts') AS tbl")
    row = cur.fetchone()
    if (row['tbl'] if isinstance(row, dict) else row[0]) is None:
        cur.execute(SCHEMA_SQL)


def resolve_host(db_cfg):
    return 'localhost' if db_cfg.get('mode') == 'localhost' else (db_cfg.get('host') or '').strip()


def is_configured(db_cfg):
    # 'saved' is only set once the user submits the DB form, so defaults never trigger connections
    return bool(db_cfg.get('saved') and resolve_host(db_cfg) and db_cfg.get('database') and db_cfg.get('user'))


def connect(db_cfg):
    host = resolve_host(db_cfg)
    if not host:
        raise ValueError('Chưa nhập địa chỉ IP/host của PostgreSQL server')
    return psycopg2.connect(
        host=host,
        port=int(db_cfg.get('port') or 5432),
        dbname=db_cfg.get('database'),
        user=db_cfg.get('user'),
        password=db_cfg.get('password') or None,
        connect_timeout=5,
    )


def test_connection(db_cfg):
    with connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute('SELECT version()')
        version = cur.fetchone()[0]
        _ensure_schema(cur)
    conn.close()
    return version.split(',')[0]


def save_transcript(db_cfg, record):
    conn = connect(db_cfg)
    try:
        with conn, conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                """INSERT INTO transcripts (text, engine, language, source, filename, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id, created_at""",
                (
                    record['text'],
                    record.get('engine'),
                    record.get('language'),
                    record.get('source'),
                    record.get('filename'),
                    record.get('confidence'),
                ),
            )
            row_id, created_at = cur.fetchone()
        return {'id': row_id, 'created_at': created_at.isoformat()}
    finally:
        conn.close()


def list_transcripts(db_cfg, limit=20):
    conn = connect(db_cfg)
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _ensure_schema(cur)
            cur.execute(
                """SELECT id, text, engine, language, source, filename, confidence, created_at
                   FROM transcripts ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
        for r in rows:
            r['created_at'] = r['created_at'].isoformat()
        return rows
    finally:
        conn.close()


def describe_error(e):
    msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    if isinstance(e, psycopg2.OperationalError):
        low = msg.lower()
        if 'password authentication failed' in low:
            return 'Sai user hoặc mật khẩu PostgreSQL'
        if 'no password supplied' in low:
            return 'Server đã kết nối được nhưng yêu cầu mật khẩu — hãy nhập mật khẩu PostgreSQL'
        if 'does not exist' in low and 'database' in low:
            return f'Database không tồn tại: {msg}'
        if 'timeout' in low or 'could not connect' in low or 'connection refused' in low:
            return f'Không kết nối được tới server (kiểm tra IP, port, firewall, pg_hba.conf): {msg}'
    return msg
