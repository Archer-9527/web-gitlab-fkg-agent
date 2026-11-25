"""Merge user-confirmed model connections; never invoke inference or replace existing secrets."""
from __future__ import annotations
import argparse, copy, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PROVIDERS={
    'fkg-deepseek':{
        'name':'DeepSeek official (FKG)',
        'package':'@opencode/ai/providers/openai-compatible',
        'settings':{'baseURL':'https://api.deepseek.com','apiKey':'{file:.secrets/deepseek.api-key}'},
        'models':{'deepseek-flash':{'modelID':'deepseek-flash','name':'DeepSeek v4 flash (user-confirmed ID)','capabilities':{'tools':True,'input':['text'],'output':['text']}}}},
    'fkg-glm':{
        'name':'GLM official Responses (FKG)',
        'package':'@opencode/ai/providers/openai-compatible/responses',
        'settings':{'baseURL':'https://open.bigmodel.cn/api/v1','apiKey':'{file:.secrets/glm.api-key}'},
        'models':{'glm-5.3':{'modelID':'glm-5.3','name':'GLM 5.3 (user-confirmed ID)','capabilities':{'tools':True,'input':['text'],'output':['text']}}}}
}
MAPPINGS={'DeepSeek v4 flash':{'providerID':'fkg-deepseek','id':'deepseek-flash'},'GLM 5.3':{'providerID':'fkg-glm','id':'glm-5.3'}}

def configure(root=ROOT,data_dir=None):
    from app.common import load,write
    from app.runtime import DEFAULT_CONFIG
    from app.store import Store
    root=Path(root).resolve();path=root/'opencode.json';config=load(path)
    merged=copy.deepcopy(config);providers=merged.setdefault('providers',{})
    for id,definition in PROVIDERS.items():
        if id in providers and providers[id]!=definition:raise ValueError('Existing provider differs; merge manually without overwriting: '+id)
        providers[id]=copy.deepcopy(definition)
    if merged!=config:
        backup=path.with_name('opencode.json.bak-'+hashlib.sha256(path.read_bytes()).hexdigest()[:12])
        if not backup.exists():backup.write_bytes(path.read_bytes())
        write(path,merged)
    secrets=root/'.secrets';secrets.mkdir(exist_ok=True)
    for name in ['deepseek.api-key','glm.api-key']:
        target=secrets/name
        if not target.exists():target.write_text('',encoding='utf-8')
    store=Store(data_dir or root/'data')
    try:runtime=store.get('config','runtime')
    except KeyError:runtime=copy.deepcopy(DEFAULT_CONFIG)
    runtime['models']=copy.deepcopy(MAPPINGS);store.put('config',runtime,id='runtime')
    write(root/'config/models.example.json',dict(models=MAPPINGS,max_tokens=runtime.get('max_tokens'),max_usd=runtime.get('max_usd'),timeout_seconds=runtime.get('timeout_seconds',900),
          note='API keys are read by OpenCode from ignored .secrets/*.api-key files, not this mapping. Endpoints/models supplied by user; live inference unverified.'))
    return {'config':str(path),'data_dir':str(store.root),'providers':list(PROVIDERS),'model_mappings':MAPPINGS,'inference_invoked':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,help='Use the same data directory as FKG_DATA_DIR in your application')
    args=parser.parse_args();print(json.dumps(configure(data_dir=args.data_dir),ensure_ascii=False,indent=2))
