from __future__ import annotations
import os
from pathlib import Path
from copy import deepcopy
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .common import ROOT, now, uid, load, canonical, sha
from .graphs import validate_graph, scaffold, merge_patch, preview_update
from .runtime import make_services, MODEL_LABELS
from .experiments import Experiments, compare_graphs
from .imports import Imports
from .documents import official_version

def create_app(services=None):
    store,docs,runner,jobs=services or make_services()
    experiments=Experiments(store,jobs);imports=Imports(store,docs)
    app=FastAPI(title='GitLab 功能图谱构建与更新智能体',version='1.0.0')
    app.state.services=(store,docs,runner,jobs)
    @app.middleware('http')
    async def local_security(request:Request,call_next):
        host=request.headers.get('host','').split(':')[0]
        if host not in {'127.0.0.1','localhost','testserver'}:return JSONResponse({'detail':'local application only'},400)
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin=request.headers.get('origin')
            if origin and origin not in {'http://'+request.headers.get('host',''),'https://'+request.headers.get('host','')}:return JSONResponse({'detail':'cross-origin writes denied'},403)
            if 'application/json' not in request.headers.get('content-type',''):return JSONResponse({'detail':'JSON required'},415)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response
    @app.exception_handler(KeyError)
    async def missing(request,exc):return JSONResponse({'detail':str(exc)},404)
    @app.exception_handler(ValueError)
    async def invalid(request,exc):return JSONResponse({'detail':str(exc)},422)
    @app.get('/')
    def home():return FileResponse(ROOT/'web/index.html')
    @app.get('/api/status')
    def status():
        try:connection=runner.check()
        except Exception as exc:connection={'connected':False,'agent_available':False,'status':'待接入','error':str(exc)}
        return {'name':app.title,'connection':connection,'model_mappings':jobs.config()['models'],'formal_experiments_completed':False,'inference':'OpenCode only; no fallback model'}
    @app.get('/api/config')
    def config():return jobs.config()
    @app.put('/api/config')
    def set_config(body:dict):
        expected=set(jobs.config())
        if set(body)-expected:raise ValueError('unknown config fields; no credentials accepted')
        cfg=jobs.config();cfg.update(body)
        if set(cfg['models'])!=set(MODEL_LABELS):raise ValueError('both experiment model labels required')
        for model in cfg['models'].values():
            if model is not None and (set(model)-{'id','providerID','variant'} or not model.get('id') or not model.get('providerID')):raise ValueError('invalid actual model reference')
        if cfg['concurrency']!=1:raise ValueError('this release enforces serial inference for reproducible usage')
        if not 1<=cfg['max_candidate_attempts']<=3 or not 5<=cfg['timeout_seconds']<=86400:raise ValueError('invalid retry/timeout bounds')
        for key in ['max_tokens','max_usd']:
            if cfg[key] is not None and cfg[key]<=0:raise ValueError('budgets must be positive or null')
        store.put('config',cfg,id='runtime');return cfg
    @app.get('/api/models')
    def models():
        try:return runner.models()
        except Exception as e:raise HTTPException(503,str(e))
    @app.get('/api/schema')
    def schema():return load(ROOT/'schema/fkg.schema.json')
    @app.get('/api/sources')
    def sources():return [{k:v for k,v in s.items() if k!='chunks'} for s in store.list('source')]
    @app.get('/api/sources/{id}')
    def source(id:str):return store.get('source',id)
    @app.post('/api/sources/local')
    def local_source(body:dict):
        if body.get('verify_official'):return docs.import_verified_local(body['path'],body['version'],body.get('repo_prefix',''),body.get('scope','Verified local selected manual input; full boundary pending'))
        return docs.import_local(body['path'],body['version'],body.get('application','GitLab'),body.get('scope','Local selected input; full boundary not confirmed'))
    @app.post('/api/sources/official')
    def official_source(body:dict):
        # Blocking work runs in FastAPI thread pool; original files are version pinned.
        version=official_version(body['url']) if body.get('url') else body['version']
        if body.get('version') and body['version']!=version:raise ValueError('version and official URL disagree')
        return imports.start(version)
    @app.get('/api/imports')
    def import_list():return store.list('import')
    @app.post('/api/imports/{id}/resume')
    def import_resume(id:str,body:dict):
        job=store.get('import',id);return imports.start(job['version'],id)
    @app.delete('/api/sources/{id}')
    def delete_source(id:str):
        if any(store.graph_source(g['graph_id'])==id for g in store.list('graph')):raise ValueError('source referenced by immutable snapshot; deletion denied')
        if any(r['request']['source_id']==id for r in store.list('run')):raise ValueError('source referenced by run; deletion denied')
        store.delete('source',id);return {'deleted':id,'raw_files':'retained for audit; no recursive deletion'}
    @app.get('/api/sources/{id}/read')
    def read(id:str,document_id:str,start:int=1,end:int|None=None):return docs.read(id,document_id,start,end)
    @app.get('/api/sources/{id}/search')
    def search_source(id:str,q:str):return docs.search(id,q)
    @app.get('/api/graphs')
    def graphs():return [{k:v for k,v in g.items() if k not in {'nodes','relations','evidence','documents'}}|{'node_count':len(g['nodes']),'relation_count':len(g['relations']),'source_id':store.graph_source(g['graph_id'])} for g in store.list('graph')]
    @app.get('/api/graphs/{id}')
    def graph(id:str):return store.get('graph',id)
    @app.get('/api/graphs/{id}/nodes')
    def nodes(id:str,parent:str|None=None,q:str='',offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=100:raise ValueError('invalid pagination')
        g=store.get('graph',id);rows=g['nodes']
        if parent:
            ids={r['target_id'] for r in g['relations'] if r['source_id']==parent and r['relation_type'] in {'CONTAINS','HAS_STEP'}};rows=[n for n in rows if n['id'] in ids]
        elif not q:rows=[n for n in rows if n['id']==g['root_module_id']]
        if q:rows=[n for n in rows if q.casefold() in canonical(n).casefold()]
        return {'items':rows[offset:offset+limit],'total':len(rows),'offset':offset,'manual_ids':sorted(store.manual_ids(id))}
    @app.get('/api/graphs/{id}/neighborhood/{node_id}')
    def neighborhood(id:str,node_id:str):
        g=store.get('graph',id);edges=[r for r in g['relations'] if node_id in {r['source_id'],r['target_id']}]
        ids={node_id}|{r[k] for r in edges for k in ['source_id','target_id']}
        return {'nodes':[n for n in g['nodes'] if n['id'] in ids],'relations':edges}
    @app.get('/api/graphs/{id}/evidence/{eid}')
    def evidence(id:str,eid:str):
        g=store.get('graph',id);e=next((x for x in g['evidence'] if x['id']==eid),None)
        if not e:raise KeyError('evidence missing')
        return dict(e,original=docs.read(store.graph_source(id),e['document_id'],e['line_start'],e['line_end']))
    @app.get('/api/graphs/{id}/export')
    def export(id:str):
        g=store.get('graph',id);errors=validate_graph(g,store.get('source',store.graph_source(id)),docs)
        if errors:raise ValueError('; '.join(errors))
        return JSONResponse(g,headers={'Content-Disposition':f'attachment; filename="{id}.json"'})
    @app.post('/api/graphs/validate')
    def validate(body:dict):
        errors=validate_graph(body['graph'],store.get('source',body['source_id']),docs);return {'valid':not errors,'errors':errors}
    @app.post('/api/graphs/import-example')
    def import_example(body:dict):
        # Explicit developer fixture only: never called by a formal generation/experiment run.
        src=docs.import_local(ROOT/'fixtures/synthetic/synthetic_manual.md','demo-1.0','Schema Demo','Controlled synthetic fixture, not GitLab')
        g=load(ROOT/'fixtures/synthetic/fkg.example.json');old_doc=g['documents'][0]['id'];g=scaffold(src,g)
        for d in g['documents']:d['processing_status']='processed'
        for e in g['evidence']:
            if e['document_id']==old_doc:e['document_id']=src['documents'][0]['id']
        errors=validate_graph(g,src,docs)
        if errors:raise ValueError('; '.join(errors))
        store.save_graph(g,src['id']);return {'graph_id':g['graph_id'],'source_id':src['id'],'purpose':'example','inference_performed':False}
    @app.post('/api/previews')
    def preview(body:dict):return preview_update(store,docs,body['base_graph_id'],body['source_id'],body['patch'],body.get('manual',False),body.get('reviewed_conflicts',[]))
    @app.get('/api/previews/{id}')
    def get_preview(id:str):return store.get('preview',id)
    @app.post('/api/previews/{id}/confirm')
    def confirm(id:str,body:dict):
        p=store.get('preview',id);src=store.get('source',p['source_id']);errors=validate_graph(p['graph'],src,docs)
        if errors:raise ValueError('; '.join(errors))
        gid=store.save_graph(p['graph'],src['id'],body.get('run_id'),p['base_graph_id'],p['operations'],p['touched'] if p['manual'] else (),confirmation=id)
        p['status']='confirmed';store.put('preview',p)
        for run in store.list('run'):
            if run.get('preview_id')==id:run.update(status='succeeded',graph_id=gid);store.put('run',run)
        return {'graph_id':gid,'preserved_base':p['base_graph_id']}
    @app.get('/api/changes')
    def changes():return store.list('change')
    @app.get('/api/runs')
    def runs():return [{k:v for k,v in r.items() if k not in {'candidate','chunk_plan','operations','batches'}} for r in store.list('run')]
    @app.get('/api/runs/{id}')
    def get_run(id:str):return store.get('run',id)
    @app.post('/api/runs')
    def submit(body:dict,request:Request):return jobs.submit(body,request.headers.get('Idempotency-Key') or uid('submission'))
    @app.post('/api/runs/{id}/cancel')
    def cancel(id:str,body:dict):return jobs.cancel(id)
    @app.post('/api/runs/{id}/resume')
    def resume(id:str,body:dict):return jobs.resume(id)
    @app.get('/api/runs/{id}/tools')
    def tool_log(id:str):return [x for x in store.list('tool') if x['run_id']==id]
    @app.post('/api/experiments')
    def start_experiment(body:dict):return experiments.start(body['source15'],body['source17'])
    @app.post('/api/experiments/{id}/resume')
    def resume_experiment(id:str,body:dict):return experiments.resume(id)
    @app.get('/api/experiments')
    def list_experiments():return [experiments.summary(e['id']) for e in store.list('experiment')]
    @app.post('/api/compare')
    def compare(body:dict):return compare_graphs(store.get('graph',body['left']),store.get('graph',body['right']),body.get('reviewed_pairs'),body.get('reference_is_reviewed',False),body.get('reviewed_relation_pairs'),body.get('node_adjudication_complete',False),body.get('relation_adjudication_complete',False))
    app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
    return app

app=create_app()
