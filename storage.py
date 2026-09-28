"""SQLite records; API keys encrypted with Windows DPAPI."""
import base64, ctypes, json, os, sqlite3, threading, uuid
from ctypes import wintypes
from pathlib import Path
from datetime import datetime, timezone
DATA = Path(os.environ.get('GUANGYU_DATA', Path(__file__).resolve().parent / 'data'))
LOCK = threading.RLock()
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
def crypt(value, decrypt=False):
    if not value: return ''
    if os.name != 'nt': raise ValueError('此版本使用 Windows DPAPI，请在 Windows 上运行。')
    raw = base64.b64decode(value) if decrypt else value.encode('utf-8')
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    lib = ctypes.WinDLL('crypt32', use_last_error=True)
    if decrypt: ok = lib.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else: ok = lib.CryptProtectData(ctypes.byref(source), 'Guangyu AI', None, None, None, 1, ctypes.byref(output))
    if not ok: raise ValueError('无法读写加密密钥，请使用保存密钥时的 Windows 用户。')
    try:
        result = ctypes.string_at(output.pbData, output.cbData)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally: ctypes.windll.kernel32.LocalFree(output.pbData)
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()
def connect():
    conn = sqlite3.connect(DATA / 'workspace.sqlite3', timeout=20, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    return conn
def init():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'media').mkdir(exist_ok=True)
    (DATA / 'uploads').mkdir(exist_ok=True)
    with connect() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript('CREATE TABLE IF NOT EXISTS providers(id TEXT PRIMARY KEY,payload TEXT NOT NULL);CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload TEXT NOT NULL);CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,updated_at TEXT NOT NULL,payload TEXT NOT NULL);')
def put(table, obj):
    if table not in ('providers','jobs','conversations'): raise ValueError('unknown table')
    payload = json.dumps(obj, ensure_ascii=False)
    with LOCK, connect() as conn:
        if table == 'providers': conn.execute('INSERT OR REPLACE INTO providers VALUES (?,?)',(obj['id'],payload))
        elif table == 'jobs': conn.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(obj['id'],obj['created_at'],payload))
        else: conn.execute('INSERT OR REPLACE INTO conversations VALUES (?,?,?)',(obj['id'],obj['updated_at'],payload))
    return obj
def get(table, identity):
    if table not in ('providers','jobs','conversations'): raise ValueError('unknown table')
    with connect() as conn: row = conn.execute(f'SELECT payload FROM {table} WHERE id=?',(identity,)).fetchone()
    return json.loads(row['payload']) if row else None
def items(table, limit=200):
    order = {'providers':'rowid','jobs':'created_at','conversations':'updated_at'}[table]
    with connect() as conn: rows = conn.execute(f'SELECT payload FROM {table} ORDER BY {order} DESC LIMIT ?',(limit,)).fetchall()
    return [json.loads(r['payload']) for r in rows]
def delete_provider(identity):
    with LOCK, connect() as conn: conn.execute('DELETE FROM providers WHERE id=?',(identity,))
def update_job(identity, **fields):
    with LOCK:
        job = get('jobs',identity)
        job.update(fields,updated_at=now())
        return put('jobs',job)
def public_provider(p):
    import capabilities, providers, image_controls, video_controls
    return {**{k:v for k,v in p.items() if k!='secret'},'has_key':bool(p.get('secret')), 'capabilities':capabilities.effective(p),'mapped_controls':capabilities.mapped_controls(p),'model_constraints':providers.model_constraints(p.get('model')),'image_controls':image_controls.options(p),'video_controls':video_controls.options(p) if p.get('kind')=='video' else None,'effective_request_timeout':providers.request_timeout(p)}
def public_job(j): return {k:v for k,v in j.items() if k not in ('provider_snapshot','messages')}
