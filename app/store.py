from __future__ import annotations
import json, sqlite3, threading
from pathlib import Path
from .common import canonical, now, uid

class Store:
    """SQLite is authoritative: graphs, operation logs and run links commit atomically."""
    def __init__(self, directory):
        self.root = Path(directory).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'fkg.sqlite3'; self.lock = threading.RLock()
        with self.db() as c:
            c.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS keys(key TEXT PRIMARY KEY, request_hash TEXT, run_id TEXT);
            CREATE TABLE IF NOT EXISTS graph_links(graph_id TEXT PRIMARY KEY, source_id TEXT, run_id TEXT, base_id TEXT);
            CREATE TABLE IF NOT EXISTS manual(graph_id TEXT, entity_id TEXT, PRIMARY KEY(graph_id,entity_id));
            ''')
    def db(self):
        c=sqlite3.connect(self.path, timeout=30); c.row_factory=sqlite3.Row; return c
    def put(self, kind, body, id=None):
        id=id or body.get('id') or uid(kind)
        with self.lock, self.db() as c:
            c.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',(kind,id,canonical(body)))
        return id
    def get(self, kind, id):
        with self.db() as c: row=c.execute('SELECT body FROM records WHERE kind=? AND id=?',(kind,id)).fetchone()
        if not row: raise KeyError(f'{kind} not found: {id}')
        return json.loads(row[0])
    def list(self, kind):
        with self.db() as c: return [json.loads(r[0]) for r in c.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid DESC',(kind,))]
    def delete(self, kind,id):
        with self.db() as c:c.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,id))
    def reserve_run(self, key, request_hash, run):
        with self.lock,self.db() as c:
            row=c.execute('SELECT request_hash,run_id FROM keys WHERE key=?',(key,)).fetchone()
            if row:
                if row[0]!=request_hash: raise ValueError('idempotency key reused with a different request')
                return row[1],False
            c.execute('INSERT INTO keys VALUES(?,?,?)',(key,request_hash,run['id']))
            c.execute('INSERT INTO records VALUES(?,?,?)',('run',run['id'],canonical(run)))
            return run['id'],True
    def graph_source(self,id):
        with self.db() as c:row=c.execute('SELECT source_id FROM graph_links WHERE graph_id=?',(id,)).fetchone()
        if not row:raise KeyError('graph has no source binding')
        return row[0]
    def manual_ids(self,id):
        with self.db() as c:return {r[0] for r in c.execute('SELECT entity_id FROM manual WHERE graph_id=?',(id,))}
    def save_graph(self, graph, source_id, run_id=None, base_id=None, changes=None, manual_ids=(), confirmation=None):
        with self.lock,self.db() as c:
            if confirmation:
                old=c.execute('SELECT body FROM records WHERE kind=? AND id=?',('confirmation',confirmation)).fetchone()
                if old:return json.loads(old[0])['graph_id']
            if c.execute('SELECT 1 FROM records WHERE kind=? AND id=?',('graph',graph['graph_id'])).fetchone():
                raise ValueError('immutable graph id already exists')
            c.execute('INSERT INTO records VALUES(?,?,?)',('graph',graph['graph_id'],canonical(graph)))
            c.execute('INSERT INTO graph_links VALUES(?,?,?,?)',(graph['graph_id'],source_id,run_id,base_id))
            inherited=self.manual_ids(base_id) if base_id else set()
            c.executemany('INSERT OR IGNORE INTO manual VALUES(?,?)',[(graph['graph_id'],x) for x in set(manual_ids)|inherited])
            if changes is not None:
                log={'id':uid('log'),'base_graph_id':base_id,'target_graph_id':graph['graph_id'],'created_at':now(),'operations':changes}
                c.execute('INSERT INTO records VALUES(?,?,?)',('change',log['id'],canonical(log)))
            if confirmation:c.execute('INSERT INTO records VALUES(?,?,?)',('confirmation',confirmation,canonical({'graph_id':graph['graph_id']})))
        return graph['graph_id']
