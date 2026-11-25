from __future__ import annotations
import difflib, re
from collections import deque
from pathlib import Path
from urllib.parse import quote, urlparse, unquote
import httpx
from .common import inside, load, write, now, sha, uid, ROOT

EXCLUDED = {'development':'product engineering, not user operations', 'architecture':'implementation architecture',
 'install':'deployment installation, outside user manual', 'update':'deployment upgrades',
 'downgrade_ee_to_ce':'deployment downgrade', 'raketasks':'maintenance scripts', '.vale':'lint configuration', '.markdownlint':'lint configuration'}
PINNED={'15.0':{'tag':'v15.0.0-ee','commit':'3b397c1753233301037d0ca3caae23ce116505d3'},
        '17.0':{'tag':'v17.0.0-ee','commit':'8c75d0bf4a4190d94326f1a854d0a102ceca4392'}}
API='https://gitlab.com/api/v4/projects/278964/repository'

def chunks(text, size=100):
    lines=text.splitlines(); headings=[]; result=[]; start=1; context=[]
    def emit(end):
        if end>=start:
            q='\n'.join(lines[start-1:end]);result.append({'line_start':start,'line_end':end,'heading_path':context.copy(),'quote':q,'fragment_sha256':sha(q)})
    fenced=False
    for i,line in enumerate(lines,1):
        if line.startswith('```'):fenced=not fenced
        m=re.match(r'^(#{1,6})\s+(.+)',line) if not fenced else None
        if m:
            emit(i-1);start=i
            headings=headings[:len(m[1])-1]+[m[2]];context=headings.copy()
        elif i-start>=size:
            emit(i-1);start=i
    emit(len(lines));return result

def manifest(documents):return sha(''.join(d['path']+'\t'+d['content_sha256']+'\n' for d in sorted(documents,key=lambda d:d['path'])))

class Documents:
    def __init__(self, store, allowed_roots=None):
        self.store=store;self.allowed=[Path(x).resolve() for x in (allowed_roots or [ROOT,ROOT.parent])]
    def source_root(self,id):return self.store.root/'sources'/id/'raw'
    def import_local(self,path,version,application='GitLab',scope='Local selected input; full boundary not confirmed',purpose='example'):
        path=Path(path).resolve()
        if not any(path.is_relative_to(b) for b in self.allowed):raise ValueError('source outside FKG_IMPORT_ROOTS')
        if not path.exists():raise ValueError('source path does not exist')
        if purpose!='example':raise ValueError('local files have unverified provenance; import official source for production')
        files=[path] if path.is_file() else sorted(path.rglob('*'))
        files=[p for p in files if p.is_file() and p.suffix.lower() in {'.md','.markdown','.txt'}]
        if not files:raise ValueError('no supported UTF-8 Markdown/text files')
        for p in files:inside(path.parent if path.is_file() else path,p)
        origin='local:'+str(path);entries=[]
        for p in files:
            rel=p.name if path.is_file() else p.relative_to(path).as_posix()
            try:entries.append((rel,p.read_bytes(),None))
            except OSError as exc:entries.append((rel,None,type(exc).__name__))
        return self._save(entries,version,application,origin,scope,purpose,None,None,[],False)
    def import_verified_local(self,path,version,repo_prefix='',scope='Verified local selected manual input; full boundary pending'):
        if version not in PINNED:raise ValueError('verified local import requires 15.0 or 17.0')
        local=self.import_local(path,version,'GitLab',scope)
        pin=PINNED[version];root=self.source_root(local['id']);entries=[]
        with httpx.Client(timeout=60,follow_redirects=True) as c:
            r=c.get(API+'/tags/'+pin['tag']);r.raise_for_status()
            if r.json()['commit']['id']!=pin['commit']:raise ValueError('tag/commit verification failed')
            for d in local['documents']:
                p=(repo_prefix.strip('/')+'/' + d['path']).lstrip('/')
                if not p.startswith('doc/') or '..' in p.split('/'):raise ValueError('provide repo_prefix so every file maps to verified doc/... path')
                raw=(root/d['path']).read_bytes();r=c.get(API+'/files/'+quote(p,safe='')+'/raw',params={'ref':pin['commit']});r.raise_for_status()
                if sha(raw)!=sha(r.content):raise ValueError('local bytes differ from pinned official file: '+p)
                entries.append((p,raw,None))
        return self._save(entries,version,'GitLab','https://gitlab.com/gitlab-org/gitlab/-/tree/'+pin['commit'],scope,'production',pin['tag'],pin['commit'],[],True)
    def _save(self,entries,version,application,origin,scope,purpose,tag,commit,excluded,verified):
        sid=uid('src');rawroot=self.source_root(sid);rawroot.mkdir(parents=True)
        docs=[];segments=[]
        for path,raw,error in entries:
            did=uid('doc');status='pending'
            if raw is not None:
                target=inside(rawroot,rawroot/path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                try:
                    text=raw.decode('utf-8');segments.extend(dict(x,id=uid('chunk'),document_id=did,path=path,status='pending') for x in chunks(text))
                except UnicodeError as exc:error=str(exc)
            docs.append({'id':did,'path':path,'locator':origin+'/'+path,'application_version':version,'content_sha256':sha(raw or b''),
                         'processing_status':'failed' if error else status,'error':error})
        source={'id':sid,'application':application,'version':version,'purpose':purpose,'created_at':now(), 'verified':verified,
                'scope_confirmed':False,'coverage_status':'partial','origin':origin,'git_tag':tag,'commit':commit,
                'scope_description':scope,'excluded_documents':excluded,'documents':docs,'manifest_sha256':manifest(docs),'chunks':segments}
        duplicate=next((s['id'] for s in self.store.list('source') if s['manifest_sha256']==source['manifest_sha256'] and s['version']==version),None)
        source['duplicate_of']=duplicate
        self.store.put('source',source);return source
    def official(self,version,progress=lambda stage,processed,total:None,import_id=None):
        if version not in PINNED:raise ValueError('supported formal versions: 15.0, 17.0')
        pin=PINNED[version];entries=[];excluded=[];page=1;paths=[]
        cache=self.store.root/'imports'/(import_id or uid('import'));cache.mkdir(parents=True,exist_ok=True)
        index_path=cache/'index.json'
        index=load(index_path) if index_path.exists() else {}
        with httpx.Client(timeout=90,follow_redirects=True) as c:
            r=c.get(API+'/tags/'+pin['tag']);r.raise_for_status()
            if r.json()['commit']['id']!=pin['commit']:raise ValueError('official tag commit mismatch')
            while True:
                progress('enumerate',len(paths),None)
                r=c.get(API+'/tree',params={'ref':pin['commit'],'path':'doc','recursive':'true','per_page':100,'page':page});r.raise_for_status();items=r.json()
                if not items:break
                for item in items:
                    p=item['path'];part=p.split('/')[1] if '/' in p else p
                    if item['type']!='blob' or not p.endswith(('.md','.markdown')):continue
                    if part in EXCLUDED:
                        excluded.append({'path':p,'reason':EXCLUDED[part]});continue
                    paths.append(p)
                page+=1
            for i,p in enumerate(paths):
                progress('download',i,len(paths));target=inside(cache,cache/p)
                try:
                    if p in index and target.exists() and sha(target.read_bytes())==index[p]:raw=target.read_bytes()
                    else:
                        r=c.get(API+'/files/'+quote(p,safe='')+'/raw',params={'ref':pin['commit']});r.raise_for_status();raw=r.content
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);index[p]=sha(raw);write(index_path,index)
                    entries.append((p,raw,None))
                except httpx.HTTPError as exc:entries.append((p,None,type(exc).__name__))
            progress('snapshot',len(paths),len(paths))
        if not entries:raise ValueError('official tree contains no in-scope documents')
        return self._save(entries,version,'GitLab','https://gitlab.com/gitlab-org/gitlab/-/tree/'+pin['commit'],
            'All Markdown under doc except enumerated engineering/deployment directories; administrator, CI, API, security and user manuals included. Boundary pending user confirmation.',
            'production',pin['tag'],pin['commit'],excluded,True)
    def read(self,sid,did,start=1,end=None):
        s=self.store.get('source',sid);d=next((d for d in s['documents'] if d['id']==did),None)
        if not d:raise ValueError('document not in this source')
        raw=inside(self.source_root(sid),self.source_root(sid)/d['path']).read_bytes()
        if sha(raw)!=d['content_sha256']:raise ValueError('stored source was modified')
        lines=raw.decode('utf-8').splitlines();end=min(end or start+99,len(lines))
        if start<1 or end<start or end-start>250:raise ValueError('invalid line window (max 251)')
        q='\n'.join(lines[start-1:end]);return {'document_id':did,'path':d['path'],'version':s['version'],'line_start':start,'line_end':end,'quote':q,'fragment_sha256':sha(q)}
    def search(self,sid,query,limit=20):
        if not query.strip():raise ValueError('empty search')
        s=self.store.get('source',sid);hits=[]
        for c in s['chunks']:
            if query.casefold() in c['quote'].casefold():hits.append(c)
            if len(hits)>=min(limit,100):break
        return hits

def diff_sources(old,new):
    a={d['path']:d for d in old['documents']};b={d['path']:d for d in new['documents']};result=[];used=set()
    for p,d in a.items():
        if p in b:
            result.append({'kind':'unchanged' if d['content_sha256']==b[p]['content_sha256'] else 'modified','old':p,'new':p});used.add(p)
        else:
            matches=[q for q,e in b.items() if q not in used and e['content_sha256']==d['content_sha256']]
            if len(matches)==1:result.append({'kind':'moved','old':p,'new':matches[0]});used.add(matches[0])
            else:result.append({'kind':'missing_unconfirmed','old':p,'new':None,'reason':'Search renamed/rewritten documents before deletion'})
    for p in b.keys()-used:
        # Approximate alignment is a candidate, never a deletion or identity decision.
        candidates=[]
        newtext='\n'.join(c['quote'] for c in new['chunks'] if c['path']==p)
        for x in result:
            if x['kind']=='missing_unconfirmed':
                oldtext='\n'.join(c['quote'] for c in old['chunks'] if c['path']==x['old'])
                ratio=difflib.SequenceMatcher(None,oldtext,newtext,autojunk=False).ratio()
                if ratio>=0.45:candidates.append({'old':x['old'],'similarity':round(ratio,3)})
        result.append({'kind':'added','old':None,'new':p,'alignment_candidates':sorted(candidates,key=lambda x:-x['similarity'])[:3]})
    old_hashes={c['fragment_sha256'] for c in old['chunks']}
    new_hashes={c['fragment_sha256'] for c in new['chunks']}
    changed_chunks=[{'id':c['id'],'path':c['path'],'line_start':c['line_start'],'line_end':c['line_end'],'heading_path':c['heading_path']} for c in new['chunks'] if c['fragment_sha256'] not in old_hashes]
    removed_chunks=[{'id':c['id'],'path':c['path'],'line_start':c['line_start'],'heading_path':c['heading_path']} for c in old['chunks'] if c['fragment_sha256'] not in new_hashes]
    return {'changed_chunks':changed_chunks,'missing_old_chunks':removed_chunks,'old_source_id':old['id'],'new_source_id':new['id'],'files':result,'scope_changed':old['scope_description']!=new['scope_description'],
            'errors':[d['path'] for d in old['documents']+new['documents'] if d['processing_status']=='failed']}


def official_version(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.netloc!='gitlab.com' or parsed.query or parsed.fragment:raise ValueError('only pinned official GitLab repository version URLs are allowed')
    prefix='/gitlab-org/gitlab/-/tree/'
    if not parsed.path.startswith(prefix):raise ValueError('expected official GitLab tree URL')
    rest=unquote(parsed.path[len(prefix):]).strip('/').split('/')
    if len(rest)>2 or (len(rest)==2 and rest[1]!='doc'):raise ValueError('official full import requires repository root or doc root, not a module subset')
    for version,pin in PINNED.items():
        if rest[0] in {pin['tag'],pin['commit']}:return version
    raise ValueError('URL is not a verified 15.0/17.0 tag or commit')
