"""Connection-only real OpenCode probe. Does NOT resume execution or invoke a model."""
import os,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.runner import OpenCodeRunner
from app.common import uid,now,ROOT,write
r=OpenCodeRunner();check=r.check();rid=uid('probe');sid='ses_'+rid;mid='msg_'+rid
created=r.request('POST','/api/session',json={'id':sid,'title':'FKG connection-only protocol probe','agent':'gitlab-fkg','location':{'directory':r.config.directory},'metadata':{'fkg_probe':True}})['data']
prompt=r.request('POST',f'/api/session/{sid}/prompt',json={'id':mid,'text':'Connection-only protocol probe; deliberately not resumed. No semantic inference requested.','resume':False})['data']
state=r.session(sid);messages=r.messages(sid);mcp=r.request('GET','/api/mcp',params=r.location())
report={'at':now(),'scope':'connection/agent/MCP discovery and durable non-executing prompt contract only; NOT runtime inference E2E',
        'connection':check,'session_id':sid,'message_id':mid,'create_returned_id':created['id'],'prompt_keys':list(prompt),
        'session_keys':list(state),'message_count':len(messages),'mcp':mcp,'model_invoked':False,'specified_models_verified':False}
write(ROOT/'docs/connection-probe.json',report);print(json.dumps(report,ensure_ascii=True,indent=2))
