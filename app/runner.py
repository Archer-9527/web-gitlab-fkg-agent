from __future__ import annotations
import json, os, time
from dataclasses import dataclass
from typing import Callable
import httpx
from .common import ROOT, load, redact

class RunnerError(RuntimeError):
    def __init__(self,message,status_code=None):
        super().__init__(message);self.status_code=status_code
class RunnerTimeout(RunnerError):pass
class RunnerCancelled(RunnerError):pass

@dataclass
class Connection:
    base_url:str='http://127.0.0.1:4096'
    directory:str=str(ROOT)
    username:str='opencode'
    password:str=''
    timeout:float=900
    poll_seconds:float=1

class OpenCodeRunner:
    """Project adapter for the verified OpenCode 2.0.32 HTTP protocol (not an official SDK class)."""
    def __init__(self,connection=None,transport=None):
        self.config=connection or Connection(base_url=os.getenv('OPENCODE_URL','http://127.0.0.1:4096'),directory=os.getenv('OPENCODE_DIRECTORY',str(ROOT)),
                                             password=os.getenv('OPENCODE_PASSWORD',''))
        self.http=httpx.Client(base_url=self.config.base_url,auth=(self.config.username,self.config.password),timeout=30,trust_env=False,transport=transport)
    def request(self,method,path,**kwargs):
        try:
            r=self.http.request(method,path,**kwargs)
            if r.status_code>=400:raise RunnerError(f'OpenCode {method} {path}: HTTP {r.status_code} (check authentication, project and contract)',status_code=r.status_code)
            if r.status_code==204:return None
            if 'json' not in r.headers.get('content-type',''):raise RunnerError('OpenCode returned non-JSON; wrong API version/path')
            return r.json()
        except httpx.TimeoutException as e:raise RunnerTimeout('OpenCode transport timeout; submission state may be unknown, resume original session') from e
        except httpx.HTTPError as e:raise RunnerError('OpenCode disconnected: '+type(e).__name__) from e
    def location(self):return {'location[directory]':self.config.directory}
    def check(self):
        info=self.request('GET','/api/info')
        if info.get('version')!='2.0.32':raise RunnerError('Unsupported OpenCode version '+str(info.get('version'))+'; revalidate protocol before use')
        spec=self.request('GET','/openapi.json')
        required={'/api/session','/api/session/{sessionID}/prompt','/api/session/{sessionID}/interrupt','/api/agent','/api/model'}
        if not required.issubset(spec.get('paths',{})):raise RunnerError('OpenCode protocol capability mismatch')
        agents=self.request('GET','/api/agent',params=self.location())
        agent=next((a for a in agents['data'] if a['id']=='gitlab-fkg'),None)
        mcp=self.request('GET','/api/mcp',params=self.location())
        connected=any(x.get('name')=='fkg' and x.get('status',{}).get('status')=='connected' for x in mcp.get('data',[]))
        request_body=(agent or {}).get('request',{}).get('body',{})
        sampling={k:request_body[k] for k in ['temperature','top_p','max_tokens','max_output_tokens','seed'] if k in request_body}
        return {'connected':True,'version':info['version'],'directory':agents.get('location'),'agent_available':agent is not None,'agent':agent and {'id':agent['id'],'steps':agent.get('steps'),'sampling':sampling},'mcp_connected':connected,
                'status':'ready' if agent else 'awaiting_agent'}
    def models(self):
        result=self.request('GET','/api/model',params=self.location())
        return [{k:m.get(k) for k in ['id','modelID','providerID','name','capabilities','enabled','family']} for m in result['data']]
    def create(self,run_id,model):
        return self.request('POST','/api/session',json={'title':'FKG '+run_id,'agent':'gitlab-fkg','model':model,
                 'location':{'directory':self.config.directory},'metadata':{'fkg_run_id':run_id}})['data']
    def submit(self,sid,message_id,text):
        # Stable client-generated message ID gives durable retry/admission identity in v2.
        return self.request('POST',f'/api/session/{sid}/prompt',json={'id':message_id,'text':text,'resume':True})['data']
    def session(self,sid):return self.request('GET',f'/api/session/{sid}')['data']
    def cancel(self,sid):return self.request('POST',f'/api/session/{sid}/interrupt',params={'resume':'false'})
    def messages(self,sid):
        rows=[];params={'limit':200,'order':'asc'}
        while True:
            result=self.request('GET',f'/api/session/{sid}/message',params=params);rows.extend(result['data'])
            cursor=result.get('cursor',{}).get('next')
            if not cursor:break
            params={'limit':200,'cursor':cursor}
        return rows
    @staticmethod
    def public_message(message):
        # Do not store model hidden reasoning or raw provider error bodies.
        return redact({k:([p for p in v if p.get('type') in {'text','tool'}] if k=='content' else v)
                       for k,v in message.items() if k in {'id','type','agent','model','content','tokens','cost','time','retry','finish'}})
    def poll(self,sid,model,cancelled=lambda:False,on_checkpoint=lambda x:None,budget=None,after_message_id=None):
        started=time.monotonic();budget=budget or {}
        while True:
            if cancelled():self.cancel(sid);raise RunnerCancelled('cancelled by user')
            state=self.session(sid);rows=self.messages(sid)
            public=[self.public_message(m) for m in rows]
            tokens=state.get('tokens');cost=state.get('cost')
            on_checkpoint({'session_id':sid,'session':{k:state.get(k) for k in ['id','model','agent','outcome','tokens','cost','time']},'messages':public})
            for m in rows:
                if m.get('type')=='assistant' and (m.get('model')!=model or m.get('agent')!='gitlab-fkg'):
                    self.cancel(sid);raise RunnerError('actual provider/model/agent differs from requested mapping')
            if tokens and budget.get('max_tokens') and tokens['input']+tokens['output']>=budget['max_tokens']:
                self.cancel(sid);raise RunnerError('token budget reached; checkpoint retained')
            if cost is not None and budget.get('max_usd') is not None and cost>=budget['max_usd']:
                self.cancel(sid);raise RunnerError('cost budget reached; checkpoint retained')
            current_rows=rows
            if after_message_id:
                pos=next((i for i,m in enumerate(rows) if m.get('id')==after_message_id),None)
                current_rows=rows[pos+1:] if pos is not None else []
            assistants=[m for m in current_rows if m.get('type')=='assistant']
            if state.get('outcome') in {'failed','interrupted'}:raise RunnerError('OpenCode execution '+state['outcome'])
            if assistants and state.get('outcome')=='succeeded':
                last=assistants[-1]
                if last.get('error'):raise RunnerError('OpenCode assistant error (provider response omitted)')
                text='\n'.join(p['text'] for p in last.get('content',[]) if p.get('type')=='text')
                tools=[p for m in rows if m.get('type')=='assistant' for p in m.get('content',[]) if p.get('type')=='tool']
                return {'text':text,'messages':public,'tools':tools,'tokens':tokens,'cost':cost,'session_id':sid,'actual_model':last.get('model')}
            if time.monotonic()-started>=self.config.timeout:
                self.cancel(sid);raise RunnerTimeout('task timeout; session and checkpoint retained')
            time.sleep(self.config.poll_seconds)
    def read_events(self,sid,after=None):
        params={'follow':'false'}
        if after is not None:params['after']=str(after)
        try:
            r=self.http.get(f'/api/experimental/session/{sid}/log',params=params);r.raise_for_status()
            return list(parse_sse(r.text))
        except httpx.HTTPError as e:raise RunnerError('event log unavailable: '+type(e).__name__) from e

def parse_sse(text):
    """SSE framing only. Preserve actual event name/ID; never invent OpenCode event names."""
    event={};data=[]
    for line in text.replace('\r\n','\n').split('\n')+['']:
        if not line:
            if data:
                raw='\n'.join(data)
                try:value=json.loads(raw)
                except json.JSONDecodeError:value=raw
                if isinstance(value,str):
                    try:value=json.loads(value)
                    except json.JSONDecodeError:pass
                yield dict(event,data=value)
            event={};data=[]
        elif not line.startswith(':'):
            key,_,v=line.partition(':');v=v.removeprefix(' ')
            if key=='data':data.append(v)
            elif key in {'event','id'}:event[key]=v
