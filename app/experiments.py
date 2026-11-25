from __future__ import annotations
import time, threading, unicodedata, re
from collections import defaultdict
from .common import uid, now, sha, canonical

class Experiments:
    def __init__(self,store,jobs):
        self.store=store;self.jobs=jobs
        for e in store.list('experiment'):
            if e['status']=='running':e.update(status='stopped',error='Application restarted; explicitly resume experiment checkpoints');store.put('experiment',e)
    def resume(self,id):
        e=self.store.get('experiment',id)
        if e['status']=='running':raise ValueError('experiment already running')
        for rid in e['runs'].values():
            if self.store.get('run',rid)['status'] in {'failed','cancelled','checkpointed'}:self.jobs.resume(rid)
        e.update(status='running',error=None);self.store.put('experiment',e)
        threading.Thread(target=self.execute,args=(e,),daemon=True).start();return e
    def start(self,s15,s17):
        a=self.store.get('source',s15);b=self.store.get('source',s17)
        if a['version']!='15.0' or b['version']!='17.0':raise ValueError('E1–E4 require 15.0 and 17.0 source versions')
        if a['purpose']!='production' or b['purpose']!='production' or not a['verified'] or not b['verified']:raise ValueError('formal experiments reject synthetic/unverified source')
        if a['scope_description']!=b['scope_description']:raise ValueError('experiment scope mismatch')
        for label in ['DeepSeek v4 flash','GLM 5.3']:
            if not self.jobs.config()['models'].get(label):raise ValueError('experiment mapping pending: '+label)
        e={'id':uid('experiment'),'source15':s15,'source17':s17,'status':'running','created_at':now(),'runs':{},'coverage':'partial; no full-coverage certificate'}
        self.store.put('experiment',e);threading.Thread(target=self.execute,args=(e,),daemon=True).start();return e
    def execute(self,e):
        try:
            for group,label,source,mode in [('E1','DeepSeek v4 flash',e['source17'],'generate'),('E2','DeepSeek v4 flash',e['source17'],'generate'),
               ('E3','GLM 5.3',e['source17'],'generate'),('E4_old','DeepSeek v4 flash',e['source15'],'generate'),('E4_update','DeepSeek v4 flash',e['source17'],'update')]:
                req={'mode':mode,'source_id':source,'model_label':label,'experiment_id':e['id'],'experiment_group':group}
                if mode=='update':req['base_graph_id']=self.store.get('run',e['runs']['E4_old'])['graph_id']
                run=self.jobs.submit(req,e['id']+':'+group);e['runs'][group]=run['id'];self.store.put('experiment',e)
                while True:
                    run=self.store.get('run',run['id'])
                    if run['status'] in {'succeeded','awaiting_confirmation'}:break
                    if run['status'] in {'failed','cancelled','checkpointed'}:raise ValueError(group+': '+run.get('error','stopped'))
                    time.sleep(.5)
                if run['status']=='awaiting_confirmation':e['status']='awaiting_E4_confirmation'
            if e['status']=='running':e['status']='succeeded'
        except Exception as exc:e['status']='stopped';e['error']=str(exc)
        e['ended_at']=now();self.store.put('experiment',e)
    def summary(self,eid):
        e=self.store.get('experiment',eid);e['statistics']={k:self.store.get('run',v).get('usage') for k,v in e['runs'].items()}
        usages=[e['statistics'].get(k) or {} for k in ['E4_old','E4_update']]
        costs=[u.get('usd') for u in usages]
        e['E4_total_usd']=sum(costs) if all(c is not None for c in costs) else None
        tokens=[u.get('tokens') for u in usages]
        e['E4_total_tokens']={k:sum(t.get(k,0) for t in tokens) for k in ['input','output','reasoning']} if all(t is not None for t in tokens) else None
        durations=[self.store.get('run',e['runs'][k]).get('duration_seconds') if k in e['runs'] else None for k in ['E4_old','E4_update']]
        e['E4_total_duration_seconds']=sum(durations) if all(v is not None for v in durations) else None
        update=self.store.get('run',e['runs']['E4_update']) if 'E4_update' in e['runs'] else None
        if update and update['status']=='succeeded':e['status']='succeeded'
        return e

def normalize(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text).casefold()).strip()
def node_keys(graph):
    nodes={n['id']:n for n in graph['nodes']};parent={r['target_id']:r['source_id'] for r in graph['relations'] if r['relation_type'] in {'CONTAINS','HAS_STEP'}}
    def path(nid,seen=None):
        seen=set() if seen is None else seen
        if nid in seen:return ('cycle',)
        seen.add(nid);n=nodes[nid];label=normalize(n['name']['text'])
        return (path(parent[nid],seen) if nid in parent else ())+((n['node_type'],label),)
    return {nid:path(nid) for nid in nodes}
def compare_graphs(left,right,reviewed_pairs=None,reference_is_reviewed=False,reviewed_relation_pairs=None,node_adjudication_complete=False,relation_adjudication_complete=False):
    """Conservative context-aware candidates + explicit adjudication, not an LLM semantic oracle."""
    lk=node_keys(left);rk=node_keys(right);lmap=defaultdict(list);rmap=defaultdict(list)
    for id,k in lk.items():lmap[k].append(id)
    for id,k in rk.items():rmap[k].append(id)
    candidates=[{'left':lmap[k][0],'right':rmap[k][0],'basis':'normalized name + full containment/owner context; needs semantic review'}
                for k in lmap.keys()&rmap.keys() if len(lmap[k])==len(rmap[k])==1]
    pairs=reviewed_pairs or [];matched={p['left']:p['right'] for p in pairs if p.get('accepted')}
    if len(set(matched.values()))!=len(matched):raise ValueError('reviewed matching must be one-to-one')
    if not set(matched)<=set(lk) or not set(matched.values())<=set(rk):raise ValueError('reviewed node mapping references unknown ID')
    def relation_key(e,mapping=None):
        s=e['source_id'];t=e['target_id']
        if mapping is not None:
            if s not in mapping or t not in mapping:return None
            s=mapping[s];t=mapping[t]
        # Conditions/bindings cannot be judged equivalent from arbitrary Claim IDs.
        return (e['relation_type'],s,t)
    relation_candidates=[]
    for l in left['relations']:
        key=relation_key(l,matched)
        if key:
            for r in right['relations']:
                if relation_key(r)==key:relation_candidates.append({'left':l['id'],'right':r['id'],'needs_guard_binding_review':True})
    # Node precision/recall ONLY when the caller supplies a reviewed reference AND adjudicated pairs.
    precision=len(matched)/len(left['nodes']) if reference_is_reviewed and node_adjudication_complete and left['nodes'] else None
    recall=len(matched)/len(right['nodes']) if reference_is_reviewed and node_adjudication_complete and right['nodes'] else None
    relation_pairs=[p for p in (reviewed_relation_pairs or []) if p.get('accepted')]
    lids={r['id'] for r in left['relations']};rids={r['id'] for r in right['relations']}
    if any(p['left'] not in lids or p['right'] not in rids for p in relation_pairs):raise ValueError('unknown reviewed relation')
    if len({p['left'] for p in relation_pairs})!=len(relation_pairs) or len({p['right'] for p in relation_pairs})!=len(relation_pairs):raise ValueError('relation mapping must be one-to-one')
    rp=len(relation_pairs)/len(lids) if reference_is_reviewed and relation_adjudication_complete and lids else None
    rr=len(relation_pairs)/len(rids) if reference_is_reviewed and relation_adjudication_complete and rids else None
    return {'left_graph_id':left['graph_id'],'right_graph_id':right['graph_id'],'node_candidates':candidates,'reviewed_node_matches':len(matched),
      'node_precision':precision,'node_recall':recall,'relation_precision':rp,'relation_recall':rr,'reviewed_relation_matches':len(relation_pairs),'relation_candidates':relation_candidates,
      'unmatched_left':[x for x in lk if x not in matched],'unmatched_right':[x for x in rk if x not in set(matched.values())],
      'note':'No automatic semantic truth judgment. E1 is not a gold standard. Adjudicate node and relation samples, including guards, workflows and output bindings. Null metrics mean no reviewed reference/labels.'}
