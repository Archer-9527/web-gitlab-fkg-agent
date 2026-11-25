from __future__ import annotations
import json, sys, traceback
from .common import ROOT, canonical, now, sha, uid
from .graphs import SCHEMA, merge_patch, validate_graph, candidate_errors

TOOL_ARGS={
 'fkg_context':{},
 'fkg_schema':{},
 'fkg_read':{'source_id':{'type':'string'},'document_id':{'type':'string'},'line_start':{'type':'integer','minimum':1},'line_end':{'type':'integer','minimum':1}},
 'fkg_search':{'source_id':{'type':'string'},'query':{'type':'string'}},
 'fkg_entities':{'query':{'type':'string'},'offset':{'type':'integer','minimum':0},'collection':{'type':'string','enum':['nodes','relations','evidence']}},
 'fkg_identity':{'kind':{'type':'string','enum':['node','workflow','claim','evidence','relation']},'semantic_key':{'type':'string'}},
 'fkg_diff':{},
 'fkg_validate':{'patch':{'type':'object'}},
 'fkg_stage':{'patch':{'type':'object'}}}
REQUIRED={'fkg_read':['source_id','document_id','line_start','line_end'],'fkg_search':['source_id','query'],
          'fkg_identity':['kind','semantic_key'],'fkg_validate':['patch'],'fkg_stage':['patch']}
DESCRIPTIONS={'fkg_context':'Read authorized run metadata, current chunk and candidate summary; no final snapshot writes.',
 'fkg_schema':'Read the immutable FKG 0.1 schema and domain rules.', 'fkg_read':'Read exact immutable original lines (max 251), with source hash and position.',
 'fkg_search':'Cross-file literal retrieval in authorized version only.', 'fkg_entities':'Paginated candidate entity lookup; compare meaning before merging.',
 'fkg_identity':'Allocate/reuse opaque identity within run, keyed by semantic identity including context, not name only.',
 'fkg_diff':'Read deterministic file alignment and direct/indirect impact.', 'fkg_validate':'Validate proposed patch, source quotes and graph invariants; no commit.',
 'fkg_stage':'Stage a validated candidate patch as an artifact for backend review; cannot save snapshots.'}

class Tools:
    def __init__(self,store,docs):self.store=store;self.docs=docs
    def call(self,name,args):
        try:
            if name not in TOOL_ARGS:raise ValueError('unknown tool')
            from jsonschema import Draft202012Validator
            schema={'type':'object','properties':dict(TOOL_ARGS[name],run_id={'type':'string'}),'required':['run_id']+REQUIRED.get(name,[]),'additionalProperties':False}
            errors=list(Draft202012Validator(schema).iter_errors(args))
            if errors:raise ValueError('invalid tool arguments: '+errors[0].message)
            return self._call(name,args)
        except Exception as exc:
            self.store.put('tool',{'id':uid('tool'),'run_id':args.get('run_id'),'name':name,'at':now(),'args_hash':sha(canonical(args)),'error':str(exc)})
            raise
    def _call(self,name,args):
        run=self.store.get('run',args['run_id'])
        if run['status'] not in {'running','queued','checkpointed'}:raise ValueError('run is not active')
        allowed={run['request']['source_id']}
        if run.get('old_source_id'):allowed.add(run['old_source_id'])
        if args.get('source_id') and args['source_id'] not in allowed:raise ValueError('source not authorized for run')
        if name=='fkg_schema':result={'schema':SCHEMA,'rules':(ROOT/'schema'/'Schema说明_v0.1.md').read_text(encoding='utf-8-sig')}
        elif name=='fkg_context':
            g=run['candidate'];result={'run_id':run['id'],'mode':run['request']['mode'],'source_id':run['request']['source_id'],
                'old_source_id':run.get('old_source_id'),'base_graph_id':run['request'].get('base_graph_id'),'chunk':run.get('current_chunk'),
                'graph':{k:v for k,v in g.items() if k not in {'nodes','relations','evidence'}},'counts':{k:len(g[k]) for k in ['nodes','relations','evidence']},
                'impact':run.get('impact'),'unresolved_evidence':run.get('pending_evidence',[]),'last_errors':run.get('last_errors',[])}
        elif name=='fkg_read':result=self.docs.read(args['source_id'],args['document_id'],args['line_start'],args['line_end'])
        elif name=='fkg_search':result=self.docs.search(args['source_id'],args['query'])
        elif name=='fkg_entities':
            rows=run['candidate'][args.get('collection','nodes')];q=args.get('query','').casefold();rows=[r for r in rows if q in canonical(r).casefold()]
            offset=args.get('offset',0);result={'items':rows[offset:offset+50],'total':len(rows),'offset':offset}
        elif name=='fkg_identity':
            key=run['id']+':'+args['kind']+':'+sha(args['semantic_key'])
            try:result=self.store.get('identity',key)
            except KeyError:
                result={'id':uid(args['kind']),'semantic_key':args['semantic_key']};self.store.put('identity',result,id=key)
        elif name=='fkg_diff':result={'diff':run.get('diff'),'impact':run.get('impact')}
        elif name in {'fkg_validate','fkg_stage'}:
            patch=args['patch'];g=merge_patch(run['candidate'],patch)
            for d in g['documents']:
                if any(e['document_id']==d['id'] for e in g['evidence']) and d['processing_status']!='failed':d['processing_status']='processed'
            errors,deferred=candidate_errors(g,self.store.get('source',run['request']['source_id']),self.docs,run,patch)
            result={'valid':not errors and not deferred,'stageable':not errors,'deferred_source_errors':deferred,'errors':errors[:60],'semantic_truth':'requires source-entailment review, not proven by validation'}
            if name=='fkg_stage':
                audit=[e for e in self.store.list('tool') if e['run_id']==run['id']]
                chunk=run.get('current_chunk',{})
                if chunk.get('document_id') and not any(e['name']=='fkg_read' and e.get('source_id')==run['request']['source_id'] and e.get('document_id')==chunk['document_id'] and e.get('line_start',10**12)<=chunk['line_start'] and e.get('line_end',0)>=chunk['line_end'] for e in audit):raise ValueError('current chunk must be read in full with fkg_read before staging')
                expected_validation=sha(canonical({'run_id':run['id'],'patch':patch}))
                if not any(e['name']=='fkg_validate' and e.get('args_hash')==expected_validation and e.get('result',{}).get('stageable') for e in audit):raise ValueError('call fkg_validate on this exact patch before staging')
                if errors:raise ValueError('cannot stage invalid candidate: '+'; '.join(errors[:10]))
                aid=uid('artifact');self.store.put('artifact',{'id':aid,'run_id':run['id'],'chunk_id':run.get('current_chunk',{}).get('id'),'patch':patch,'created_at':now()});result['artifact_id']=aid
        else:raise ValueError('unknown tool')
        event={'id':uid('tool'),'run_id':run['id'],'name':name,**{k:args[k] for k in ['source_id','document_id','line_start','line_end'] if k in args},'args_hash':sha(canonical(args)),'at':now(),'result':result}
        # Schema responses are immutable and large; hash instead of copying on each call.
        if name=='fkg_schema':event['result']={'schema_sha256':sha(canonical(SCHEMA))}
        self.store.put('tool',event);return result

def serve():
    """MCP stdio JSON-RPC transport: newline framed, stdout exclusively protocol messages."""
    from .runtime import make_services
    store,docs,_,_=make_services(start_worker=False);tools=Tools(store,docs)
    for line in sys.stdin:
        try:
            req=json.loads(line);method=req.get('method');id=req.get('id');params=req.get('params',{})
            if id is None:continue
            if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'gitlab-fkg-tools','version':'1.0.0'}}
            elif method=='ping':result={}
            elif method=='tools/list':
                result={'tools':[{'name':name,'description':DESCRIPTIONS[name], 'inputSchema':{'type':'object','properties':dict(props,run_id={'type':'string'}),'required':['run_id']+REQUIRED.get(name,[]),'additionalProperties':False}} for name,props in TOOL_ARGS.items()]}
            elif method=='tools/call':
                try:value=tools.call(params['name'],params.get('arguments',{}));result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
                except Exception as exc:result={'content':[{'type':'text','text':str(exc)}],'isError':True}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':id,'error':{'code':-32601,'message':'Method not found'}}),flush=True);continue
            print(json.dumps({'jsonrpc':'2.0','id':id,'result':result},ensure_ascii=False),flush=True)
        except Exception:
            print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'invalid request'}}),flush=True)
if __name__=='__main__':serve()
