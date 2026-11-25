"""Exercise the running real application HTTP service; controlled fixture, no model inference."""
import json,httpx
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
with httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False,timeout=30) as c:
 def get(p):r=c.get(p);r.raise_for_status();return r.json()
 def post(p,b):r=c.post(p,json=b);r.raise_for_status();return r.json()
 fixture=post('/api/graphs/import-example',{});gid=fixture['graph_id'];g=get('/api/graphs/'+gid)
 root=get('/api/graphs/'+gid+'/nodes')['items'][0];neighborhood=get('/api/graphs/'+gid+'/neighborhood/'+root['id'])
 evidence=get('/api/graphs/'+gid+'/evidence/'+g['evidence'][0]['id']);after=deepcopy(root);after['description']=deepcopy(root['name'])
 preview=post('/api/previews',{'base_graph_id':gid,'source_id':fixture['source_id'],'manual':True,'patch':{'operations':[{'collection':'nodes','op':'replace','id':root['id'],'before':root,'after':after,'reason':'Controlled HTTP acceptance exercise; not GitLab knowledge'}]}})
 confirmed=post('/api/previews/'+preview['id']+'/confirm',{});assert get('/api/graphs/'+gid)==g
 exported=get('/api/graphs/'+confirmed['graph_id']+'/export');assert exported['lineage_id']==g['lineage_id']
 invalid=post('/api/graphs/validate',{'source_id':fixture['source_id'],'graph':dict(g,relations=[dict(g['relations'][0],target_id='missing')]+g['relations'][1:])});assert not invalid['valid']
 report={'at':datetime.now(timezone.utc).isoformat(),'mode':'real HTTP service / synthetic fixture / no model',
 'base_graph_id':gid,'new_graph_id':confirmed['graph_id'],'source_id':fixture['source_id'],'preview_id':preview['id'],
 'checks':{'tree':bool(root),'neighborhood':bool(neighborhood['relations']),'original_quote':evidence['original']['quote']==g['evidence'][0]['quote'],
 'valid_edit_confirmed':True,'old_snapshot_retained':True,'json_export_valid':True,'invalid_dangling_relation_rejected':True},
 'browser_visual_verified':False,'runtime_model_tool_loop_verified':False}
 Path('docs/http-acceptance.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(report,ensure_ascii=True))
