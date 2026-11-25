from __future__ import annotations
import json, os, queue, threading, time
from copy import deepcopy
from .common import ROOT, canonical, load, now, sha, uid
from .documents import Documents, diff_sources
from .graphs import affected_entities, scaffold, merge_patch, rebase_evidence, validate_graph, preview_update, candidate_errors
from .store import Store
from .runner import OpenCodeRunner, RunnerError, RunnerTimeout, RunnerCancelled

MODEL_LABELS=['DeepSeek v4 flash','GLM 5.3']
DEFAULT_CONFIG={'models':{name:None for name in MODEL_LABELS},'max_tokens':None,'max_usd':None,'timeout_seconds':900,
                'max_candidate_attempts':3,'concurrency':1,'sampling':'Configured in OpenCode agent/provider request; application does not silently override','opencode_retry':'managed by OpenCode; observed message.retry logged, unknown if unavailable'}

class Jobs:
    def __init__(self,store,docs,runner=None,start=True):
        self.store=store;self.docs=docs;self.runner=runner or OpenCodeRunner();self.queue=queue.Queue();self.worker=None
        for r in (store.list('run') if start else []):
            if r['status'] in {'running','queued'}:
                r['status']='checkpointed';r['error']='Application restarted; resume explicitly using original session/checkpoint';store.put('run',r)
        if start:self.worker=threading.Thread(target=self.loop,daemon=True);self.worker.start()
    def config(self):
        try:return self.store.get('config','runtime')
        except KeyError:return deepcopy(DEFAULT_CONFIG)
    def submit(self,request,key):
        if request['mode'] not in {'generate','update'}:raise ValueError('invalid mode')
        src=self.store.get('source',request['source_id']);config=self.config();label=request['model_label'];model=config['models'].get(label)
        if not model or not model.get('providerID') or not model.get('id'):raise ValueError('experiment model mapping pending: '+label)
        if request['mode']=='update':
            base=self.store.get('graph',request['base_graph_id']);old=self.store.get('source',self.store.graph_source(base['graph_id']))
            if base['application']!=src['application']:raise ValueError('source application mismatch')
            if old['scope_description']!=src['scope_description']:raise ValueError('update source scope mismatch')
        if any(d['processing_status']=='failed' for d in src['documents']):raise ValueError('source contains failed files; fix or reimport before inference')
        rid=uid('run');run={'id':rid,'status':'queued','request':request,'requested_model':model,'config':config,'created_at':now(),
                           'sessions':[],'batches':[],'completed_chunks':[],'artifacts':[],'progress':0,'usage':{'tokens':None,'usd':None},'retries':0,
                           'input':{'source_id':src['id'],'manifest_sha256':src['manifest_sha256'],'scope':src['scope_description'],'commit':src['commit'],'document_count':len(src['documents']),'chunk_count':len(src['chunks'])},
                           'implementation':{'schema':sha((ROOT/'schema/fkg.schema.json').read_bytes()),'prompt':sha((ROOT/'instructions/gitlab-fkg.md').read_bytes()),'tools':'1.0.0','agent':'gitlab-fkg'}}
        id,fresh=self.store.reserve_run(key,sha(canonical(request)),run)
        if fresh:self.queue.put(id)
        return self.store.get('run',id)
    def resume(self,rid):
        r=self.store.get('run',rid)
        if r['status'] not in {'failed','checkpointed','cancelled'}:raise ValueError('run is not resumable')
        r['status']='queued';r['error']=None;r['cancel_requested']=False;r['retries']+=1;self.store.put('run',r);self.queue.put(rid);return r
    def cancel(self,rid):
        r=self.store.get('run',rid);r['cancel_requested']=True;self.store.put('run',r)
        if r.get('active_session'):
            self.runner.cancel(r['active_session'])
        return {'id':rid,'cancel_requested':True}
    def loop(self):
        while True:
            rid=self.queue.get()
            try:self.execute(rid)
            except Exception as exc:
                r=self.store.get('run',rid);r.update(status='checkpointed' if isinstance(exc,(RunnerTimeout,RunnerError)) else 'failed',error=str(exc),ended_at=now())
                if isinstance(exc,RunnerCancelled):r['status']='cancelled'
                self.store.put('run',r)
            finally:self.queue.task_done()
    def _save(self,r):
        with self.store.lock:
            existing=self.store.get('run',r['id'])
            if existing.get('cancel_requested'):r['cancel_requested']=True
            self.store.put('run',r)
    def _cancelled(self,rid):return self.store.get('run',rid).get('cancel_requested',False)
    def _collect_usage(self,r):
        states=[b.get('checkpoint',{}).get('session',{}) for b in r['batches']+r.get('retired_sessions',[])]
        tokens=[s.get('tokens') for s in states];cost=[s.get('cost') for s in states]
        r['usage']={'tokens':({'input':sum(t['input'] for t in tokens),'output':sum(t['output'] for t in tokens),
                     'reasoning':sum(t.get('reasoning',0) for t in tokens)} if tokens and all(t is not None for t in tokens) else None),
                    'usd':sum(cost) if cost and all(c is not None for c in cost) and any(c!=0 for c in cost) else None,
                    'reported_opencode_usd':sum(cost) if cost and all(c is not None for c in cost) else None,
                    'cost_caveat':'OpenCode computed session cost, not reconciled invoice; all-zero cost without confirmed pricing is unknown, not free',
                    'basis':'OpenCode cumulative session usage, counted once per isolated session; excludes Codex development; retries within session included',
                    'app_retries':r['retries'],'opencode_retry_observations':sum(bool(m.get('retry')) for b in r['batches'] for m in b.get('checkpoint',{}).get('messages',[]))}
    def execute(self,rid):
        r=self.store.get('run',rid)
        if r.get('cancel_requested'):raise RunnerCancelled('cancelled before execution')
        status=self.runner.check()
        if not status['agent_available']:raise RunnerError('gitlab-fkg Agent not discovered: apply project-local config and verify directory')
        if status.get('mcp_connected') is False:raise RunnerError('fkg MCP not connected yet; wait for discovery and resume')
        r['runtime_agent']=status.get('agent')
        available=self.runner.models();model=r['requested_model']
        if not any(m['id']==model['id'] and m['providerID']==model['providerID'] for m in available):raise RunnerError('actual model mapping not available in OpenCode project')
        selected=next(m for m in available if m['id']==model['id'] and m['providerID']==model['providerID'])
        if selected.get('enabled') is False or selected.get('capabilities',{}).get('tools') is False:raise RunnerError('selected actual model is disabled or does not support tools')
        r['resolved_model_metadata']=selected
        self.runner.config.timeout=r['config']['timeout_seconds']
        src=self.store.get('source',r['request']['source_id']);r.update(status='running',opencode_version=status['version'],started_at=r.get('started_at',now()))
        mode=r['request']['mode']
        if 'candidate' not in r:
            base=self.store.get('graph',r['request']['base_graph_id']) if mode=='update' else None
            r['candidate']=scaffold(src,base)
            if base:
                old=self.store.get('source',self.store.graph_source(base['graph_id']));r['old_source_id']=old['id'];r['diff']=diff_sources(old,src)
                if r['diff']['errors']:raise ValueError('parse failures in old/new source block update')
                r['impact']=affected_entities(base,r['diff']);r['pending_evidence'],r['metadata_operations']=rebase_evidence(base,r['candidate'],old,src,self.docs)
                paths={x['new'] for x in r['diff']['files'] if x['kind'] not in {'unchanged','moved'} and x['new']}
                changed_ids={c['id'] for c in r['diff']['changed_chunks']}
                r['chunk_plan']=[c for c in src['chunks'] if c['id'] in changed_ids]
                # Deletions or metadata-only moves still require agent analysis, without re-extracting unchanged manuals.
                if not r['chunk_plan']:r['chunk_plan']=[{'id':'diff_review','path':None,'kind':'diff_review'}]
            else:r['chunk_plan']=src['chunks']
            r['operations']=[]
        self._save(r)
        for chunk in r['chunk_plan']:
            if chunk['id'] in r['completed_chunks']:continue
            if self._cancelled(rid):raise RunnerCancelled('cancelled')
            r['current_chunk']=chunk;self._save(r)
            batch=next((b for b in r['batches'] if b['chunk_id']==chunk['id'] and not b.get('done')),None)
            if batch is None:
                # Persist identity before network creation: create uses supplied session ID for idempotency.
                batch={'chunk_id':chunk['id'],'session_id':'ses_'+sha(rid+chunk['id'])[:32],'message_id':'msg_'+sha(rid+chunk['id'])[:32],'attempt':0,'submitted':False,'admission':'new'}
                r['batches'].append(batch);self._save(r)
            sid=batch['session_id'];r['active_session']=sid;self._save(r)
            try:
                existing_session=self.runner.session(sid)
                if existing_session.get('outcome') in {'interrupted','failed'} and batch['submitted']:
                    previous=batch['message_id'];batch['submitted']=False;batch['admission']='new';batch['attempt']=0
                    batch['message_id']='msg_'+sha(rid+chunk['id']+'resume'+str(r['retries']))[:32]
                    next(x for x in r['sessions'] if x['session_id']==sid)['resumes'].append({'previous_message_id':previous,'message_id':batch['message_id'],'reason':'explicit continuation from persisted candidate in original session','at':now()});self._save(r)
            except RunnerError as exc:
                # Only confirmed 404 permits a new session; other failures must not fork or duplicate.
                if exc.status_code!=404:raise
                if any(x['session_id']==sid and x.get('state')=='created' for x in r['sessions']):
                    oldsid=sid;r.setdefault('retired_sessions',[]).append({'session_id':sid,'checkpoint':deepcopy(batch.get('checkpoint',{}))})
                    sid='ses_'+sha(rid+chunk['id']+'replacement'+str(len(r['retired_sessions'])))[:32]
                    batch.update(session_id=sid,message_id='msg_'+sha(sid)[:32],submitted=False,admission='new',attempt=0,checkpoint={})
                    r['active_session']=sid;r['sessions'].append({'session_id':sid,'chunk_id':chunk['id'],'state':'creating','resumes':[],'replaces_session_id':oldsid,'restore_basis':'persistent application candidate, not restored OpenCode context'});self._save(r)
                if not any(x['session_id']==sid for x in r['sessions']):
                    r['sessions'].append({'session_id':sid,'chunk_id':chunk['id'],'state':'creating','resumes':[]});self._save(r)
                created=self.runner.request('POST','/api/session',json={'id':sid,'title':'FKG '+rid,'agent':'gitlab-fkg','model':model,'location':{'directory':self.runner.config.directory},'metadata':{'fkg_run_id':rid}})['data']
                if created['id']!=sid:raise RunnerError('session idempotency contract mismatch')
                next(x for x in r['sessions'] if x['session_id']==sid)['state']='created';self._save(r)
            while batch['attempt']<r['config']['max_candidate_attempts']:
                if batch.get('admission')=='unknown':
                    admitted=any(m.get('id')==batch['message_id'] for m in self.runner.messages(sid))
                    if admitted:batch['submitted']=True;batch['admission']='accepted';self._save(r)
                if not batch['submitted']:
                    text='Task run_id='+rid+'. Call fkg_context and fkg_schema. Current chunk '+canonical(chunk)+'. Mode '+mode+'. Candidate attempt '+str(batch['attempt']+1)+'. Read original, extract or locally update, validate and stage. Return only artifact_id JSON. Last errors: '+canonical(r.get('last_errors',[]))
                    batch['admission']='unknown';self._save(r)
                    self.runner.submit(sid,batch['message_id'],text);batch['submitted']=True;batch['admission']='accepted';self._save(r)
                def checkpoint(value):
                    batch['checkpoint']=value;self._collect_usage(r);self._save(r)
                prior_tokens=sum((b.get('checkpoint',{}).get('session',{}).get('tokens') or {}).get('input',0)+(b.get('checkpoint',{}).get('session',{}).get('tokens') or {}).get('output',0) for b in r['batches']+r.get('retired_sessions',[]) if b is not batch)
                max_tokens=r['config'].get('max_tokens');max_usd=r['config'].get('max_usd')
                prior_usd=sum(b.get('checkpoint',{}).get('session',{}).get('cost') or 0 for b in r['batches']+r.get('retired_sessions',[]) if b is not batch)
                if (max_tokens and prior_tokens>=max_tokens) or (max_usd is not None and prior_usd>=max_usd):raise RunnerError('aggregate budget reached; checkpoint retained')
                result=self.runner.poll(sid,model,lambda:self._cancelled(rid),checkpoint,
                     {'max_tokens':max_tokens-prior_tokens if max_tokens else None,'max_usd':max_usd-prior_usd if max_usd is not None else None},after_message_id=batch['message_id'])
                try:
                    data=json.loads(result['text'].strip());artifact=self.store.get('artifact',data['artifact_id'])
                    if artifact['run_id']!=rid or artifact['chunk_id']!=chunk['id']:raise ValueError('artifact run/chunk mismatch')
                    calls=[p for p in result['tools'] if p.get('state',{}).get('status')=='completed']
                    if not any('fkg_read' in p.get('name','') for p in calls) and chunk.get('document_id'):raise ValueError('no runtime original-source read tool evidence')
                    if not any('fkg_validate' in p.get('name','') for p in calls):raise ValueError('no runtime validation tool evidence')
                    g=merge_patch(r['candidate'],artifact['patch'])
                    for d in g['documents']:
                        if any(e['document_id']==d['id'] for e in g['evidence']) and d['processing_status']!='failed':d['processing_status']='processed'
                    errors,deferred=candidate_errors(g,src,self.docs,r,artifact['patch'])
                    batch['deferred_source_errors']=deferred
                    if errors:raise ValueError('; '.join(errors[:20]))
                    if hasattr(self.runner,'read_events'):
                        try:
                            events=self.runner.read_events(sid)
                            batch['events']=[{'id':e.get('id'),'event':e.get('event'),'data_sha256':sha(canonical(e.get('data')))} for e in events]
                        except RunnerError as exc:batch['event_error']=str(exc)
                    r['candidate']=g;r['operations'].extend(artifact['patch']['operations']);r['artifacts'].append(artifact['id']);r['completed_chunks'].append(chunk['id']);batch['done']=True
                    r['progress']=len(r['completed_chunks'])/len(r['chunk_plan']);r['last_errors']=[];self._save(r);break
                except (ValueError,KeyError) as exc:
                    r['last_errors']=[str(exc)];batch['attempt']+=1;r['retries']+=1;batch['submitted']=False;batch['message_id']='msg_'+sha(rid+chunk['id']+str(batch['attempt']))[:32];self._save(r)
            if not batch.get('done'):raise ValueError('bounded correction exhausted: '+canonical(r.get('last_errors')))
        if not r['completed_chunks']:raise ValueError('no document chunks processed')
        if self._cancelled(rid):raise RunnerCancelled('cancelled before commit')
        if mode=='generate':
            g=r['candidate']
            for document in g['documents']:
                if all(c['id'] in r['completed_chunks'] for c in src['chunks'] if c['document_id']==document['id']) and document['processing_status']!='failed':document['processing_status']='processed'
            errors=validate_graph(g,src,self.docs)
            if errors:raise ValueError('; '.join(errors[:40]))
            self.store.save_graph(g,src['id'],rid);r['graph_id']=g['graph_id'];r['status']='succeeded'
        else:
            p=preview_update(self.store,self.docs,r['request']['base_graph_id'],src['id'],{'operations':r['operations']})
            r['preview_id']=p['id'];r['status']='awaiting_confirmation'
        r['active_session']=None;r['ended_at']=now();r['duration_seconds']=(__import__('datetime').datetime.fromisoformat(r['ended_at'])-__import__('datetime').datetime.fromisoformat(r['started_at'])).total_seconds()
        self._collect_usage(r);self._save(r)

def make_services(start_worker=True):
    store=Store(os.getenv('FKG_DATA_DIR',str(ROOT/'data')))
    allowed=os.getenv('FKG_IMPORT_ROOTS','').split(os.pathsep) if os.getenv('FKG_IMPORT_ROOTS') else None
    docs=Documents(store,allowed);runner=OpenCodeRunner();jobs=Jobs(store,docs,runner,start=start_worker)
    return store,docs,runner,jobs
