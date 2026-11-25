from __future__ import annotations
from copy import deepcopy
import importlib.util
from pathlib import Path
from collections import defaultdict, deque
from .common import ROOT, load, uid, now, sha, canonical
from .documents import diff_sources

spec=importlib.util.spec_from_file_location('original_validator',ROOT/'schema/validate_fkg.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
SCHEMA=load(ROOT/'schema/fkg.schema.json')
COLLECTIONS=('nodes','relations','evidence')

def walk(x):yield from original.walk(x)
def business(value):
    if isinstance(value,list):return [business(v) for v in value]
    if isinstance(value,dict):return {k:business(v) for k,v in value.items() if k not in {'support','document_order'}}
    return value

def scaffold(source,base=None):
    g=deepcopy(base) if base else {'schema_version':'0.1.0','lineage_id':uid('lineage'),'nodes':[],'relations':[],'evidence':[],'root_module_id':''}
    g.update(graph_id=uid('graph'),application=source['application'],application_version=source['version'],created_at=now(),purpose=source['purpose'],coverage_status='partial',
             documents=deepcopy(source['documents']),source_snapshot={k:source[k] for k in ['origin','git_tag','commit','manifest_sha256','scope_description','excluded_documents']})
    return g

def validate_graph(graph,source,documents):
    errors=original.validate(graph,SCHEMA,documents.source_root(source['id']))
    if errors:return errors
    expected={d['id']:(d['path'],d['content_sha256'],d['application_version']) for d in source['documents']}
    actual={d['id']:(d['path'],d['content_sha256'],d['application_version']) for d in graph['documents']}
    if expected!=actual:errors.append('source manifest/document binding mismatch')
    if graph['application']!=source['application'] or graph['application_version']!=source['version']:errors.append('source application/version mismatch')
    if graph['purpose']!=source['purpose']:errors.append('source purpose mismatch')
    for k in ['origin','git_tag','commit','manifest_sha256','scope_description','excluded_documents']:
        if graph['source_snapshot'][k]!=source[k]:errors.append('source snapshot mismatch: '+k)
    if graph['purpose']=='production' and not source['verified']:errors.append('unverified production provenance')
    if graph['coverage_status']=='complete':errors.append('complete coverage requires a separately reviewed coverage certificate; automatic runs remain partial')
    # Review acceptance is a human action, never model self-certification (enforced on patches).
    for e in graph['evidence']:
        found=next(d for d in source['documents'] if d['id']==e['document_id'])
        if e['line_start']<1 or found['processing_status']=='failed':errors.append('invalid source evidence: '+e['id'])
    return errors

def merge_patch(graph,patch,allow_accepted=False):
    g=deepcopy(graph)
    if set(patch)-{'operations','root_module_id','summary','decisions'}:raise ValueError('unexpected patch fields')
    ops=patch.get('operations',[])
    for op in ops:
        if op.get('collection') not in COLLECTIONS:raise ValueError('unsupported collection')
        if op.get('op') not in {'add','replace','remove'}:raise ValueError('unsupported operation')
        if not op.get('reason'):raise ValueError('operation reason required')
        rows=g[op['collection']];idx=next((i for i,x in enumerate(rows) if x['id']==op['id']),None)
        if op['op']=='add':
            if idx is not None:
                if rows[idx]==op.get('after'):continue
                raise ValueError('add ID already exists')
            if op.get('after',{}).get('id')!=op['id']:raise ValueError('add ID mismatch')
            rows.append(deepcopy(op['after']))
        else:
            if idx is None:raise ValueError('operation ID missing')
            if op.get('before')!=rows[idx]:raise ValueError('optimistic before/after conflict: '+op['id'])
            if op['op']=='remove':rows.pop(idx)
            else:
                if op.get('after',{}).get('id')!=op['id']:raise ValueError('stable identity must not be replaced')
                rows[idx]=deepcopy(op['after'])
        if op.get('after') and not allow_accepted:
            old_accepted={canonical(x) for x in walk(op.get('before',{})) if x.get('review_status')=='accepted'}
            if any(x.get('review_status')=='accepted' and canonical(x) not in old_accepted for x in walk(op['after'])):
                raise ValueError('Agent cannot self-accept knowledge')
    if 'root_module_id' in patch:g['root_module_id']=patch['root_module_id']
    return g

def affected_entities(graph,diff):
    changed={x['old'] for x in diff['files'] if x['kind'] not in {'unchanged','moved'}}
    docs={d['id'] for d in graph['documents'] if d['path'] in changed}
    ev={e['id'] for e in graph['evidence'] if e['document_id'] in docs}
    direct={n['id'] for n in graph['nodes'] if any(ev.intersection(x.get('evidence_ids',[])) for x in walk(n))}
    direct|={r[k] for r in graph['relations'] if ev.intersection(r['support']['evidence_ids']) for k in ['source_id','target_id']}
    adj=defaultdict(list)
    for r in graph['relations']:
        if r['relation_type'] in {'CONTAINS','HAS_STEP','NEXT_STEP'}:adj[r['source_id']].append((r['target_id'],r['id']))
        else:adj[r['target_id']].append((r['source_id'],r['id']))
    impacted=set(direct);queue=deque(direct);reasons=[]
    while queue:
        p=queue.popleft()
        for q,rid in adj[p]:
            if q not in impacted:impacted.add(q);queue.append(q);reasons.append({'entity_id':q,'via':rid,'from':p})
    return {'direct':sorted(direct),'indirect':sorted(impacted-direct),'reasons':reasons}

def rebase_evidence(base,candidate,old,new,docs):
    diff=diff_sources(old,new);mapping={x['old']:x['new'] for x in diff['files'] if x['new'] and x['old']}
    olddocs={d['id']:d for d in old['documents']};newdocs={d['path']:d for d in new['documents']}
    pending=[];changes=[]
    for e in candidate['evidence']:
        original_e=deepcopy(e);oldpath=olddocs[e['document_id']]['path'];path=mapping.get(oldpath)
        targets=[newdocs[path]] if path in newdocs else list(newdocs.values())
        matches=[]
        for d in targets:
            if d['processing_status']=='failed':continue
            raw=(docs.source_root(new['id'])/d['path']).read_text(encoding='utf-8').splitlines();needle=e['quote'].splitlines()
            for i in range(len(raw)-len(needle)+1):
                if raw[i:i+len(needle)]==needle:matches.append((d['id'],i+1,i+len(needle)))
        if len(matches)==1:
            e['document_id'],e['line_start'],e['line_end']=matches[0]
            if e!=original_e:changes.append({'collection':'evidence','op':'replace','id':e['id'],'before':original_e,'after':deepcopy(e),'reason':'exact quote relocation (metadata only)'})
        else:pending.append(e['id'])
    return pending,changes

def preview_update(store,docs,base_id,new_source_id,patch,manual=False,reviewed_conflicts=()):
    base=store.get('graph',base_id);old=store.get('source',store.graph_source(base_id));new=store.get('source',new_source_id)
    if base['source_snapshot']['manifest_sha256']!=old['manifest_sha256']:raise ValueError('old graph/source binding mismatch')
    if old['application']!=new['application']:raise ValueError('different application')
    diff=diff_sources(old,new)
    if diff['errors']:raise ValueError('failed documents prevent safe update')
    if diff['scope_changed'] and not manual:raise ValueError('scope changed: confirm and align scope before automatic update')
    g=scaffold(new,base);pending,metadata=rebase_evidence(base,g,old,new,docs)
    impact=affected_entities(base,diff);allowed=set(impact['direct']+impact['indirect'])
    touched={op['id'] for op in patch['operations']}
    conflicts=sorted(touched & store.manual_ids(base_id)-set(reviewed_conflicts))
    if conflicts:raise ValueError('manual edit conflicts require explicit review: '+','.join(conflicts))
    oldnodes={n['id']:n for n in base['nodes']}
    oldrelations={r['id']:r for r in base['relations']}
    for op in patch['operations']:
        if op['collection']=='nodes' and op['id'] in oldnodes and op['id'] not in allowed and not manual:
            if business(op.get('after'))!=business(oldnodes[op['id']]):raise ValueError('outside incremental impact scope: '+op['id'])
        if op['collection']=='relations' and op['id'] in oldrelations and not manual:
            existing=oldrelations[op['id']]
            if not {existing['source_id'],existing['target_id']}&allowed and business(op.get('after'))!=business(existing):raise ValueError('unaffected relation cannot change: '+op['id'])
        if op['op']=='remove' and not manual:
            if not op.get('deletion_confirmed') or not op.get('new_evidence_ids'):raise ValueError('deletion needs explicit new-version evidence, not missing text')
    g=merge_patch(g,patch,allow_accepted=manual)
    # A stale evidence ID must be replaced or removed, never quietly reassigned.
    for eid in pending:
        if not any(o['id']==eid and o['collection']=='evidence' for o in patch['operations']):raise ValueError('unresolved source relocation: '+eid)
    active_docs={e['document_id'] for e in g['evidence']}
    for d in g['documents']:
        if d['id'] in active_docs and d['processing_status']!='failed':d['processing_status']='processed'
    ev={e['id'] for e in g['evidence']}
    for op in patch['operations']:
        if op['op']=='remove' and not manual and not set(op['new_evidence_ids']).issubset(ev):raise ValueError('invalid deletion evidence references')
    errors=validate_graph(g,new,docs)
    if errors:raise ValueError('\n'.join(errors[:40]))
    pid=uid('preview');p={'id':pid,'base_graph_id':base_id,'target_graph_id':g['graph_id'],'source_id':new_source_id,'graph':g,
         'operations':metadata+patch['operations'],'diff':diff,'impact':impact,'manual':manual,'touched':sorted(touched),'status':'awaiting_confirmation','created_at':now()}
    store.put('preview',p);return p


def candidate_errors(graph,source,documents,run,patch):
    errors=validate_graph(graph,source,documents)
    if run['request']['mode']!='update':return errors,[]
    plan=run.get('chunk_plan',[])
    if not plan or run.get('current_chunk',{}).get('id')==plan[-1]['id']:return errors,[]
    touched={op['id'] for op in patch.get('operations',[]) if op['collection']=='evidence'}
    untouched=set(run.get('pending_evidence',[]))-touched
    permitted={f'{label}: {eid}' for label in ['unknown document','source quote mismatch'] for eid in untouched}
    return [e for e in errors if e not in permitted],[e for e in errors if e in permitted]
