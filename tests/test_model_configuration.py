import copy,json,importlib.util
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from app.common import ROOT,load
from app.store import Store
from scripts.configure_models import configure,PROVIDERS,MAPPINGS

def test_provider_contract_and_protocol_selection():
    spec=load(ROOT/'docs/upstream/opencode-v2.0.32.openapi.json')
    validator=Draft202012Validator({'$ref':'#/components/schemas/Config.ProviderEncoded','components':spec['components']})
    for definition in PROVIDERS.values():assert not list(validator.iter_errors(definition))
    assert PROVIDERS['fkg-deepseek']['package']=='@opencode/ai/providers/openai-compatible'
    assert PROVIDERS['fkg-glm']['package']=='@opencode/ai/providers/openai-compatible/responses'
    assert PROVIDERS['fkg-glm']['settings']['baseURL']=='https://open.bigmodel.cn/api/v1'

def test_config_merge_preserves_agent_other_provider_and_existing_key(tmp_path):
    cfg={'agents':{'gitlab-fkg':{'system':'original instructions'}},'mcp':{'servers':{'fkg':{'command':['existing-python']}}},'providers':{'user-provider':{'name':'keep me'}}}
    (tmp_path/'opencode.json').write_text(json.dumps(cfg),encoding='utf-8')
    secrets=tmp_path/'.secrets';secrets.mkdir();(secrets/'deepseek.api-key').write_text('TEST_ONLY_NOT_A_REAL_KEY',encoding='utf-8')
    store=Store(tmp_path/'data');store.put('config',{'models':{},'max_tokens':1234,'timeout_seconds':200},id='runtime')
    configure(tmp_path);first=load(tmp_path/'opencode.json');configure(tmp_path)
    assert first==load(tmp_path/'opencode.json')
    assert first['agents']==cfg['agents'] and first['mcp']==cfg['mcp'] and first['providers']['user-provider']==cfg['providers']['user-provider']
    assert (secrets/'deepseek.api-key').read_text()=='TEST_ONLY_NOT_A_REAL_KEY'
    assert (secrets/'glm.api-key').read_text()==''
    current=store.get('config','runtime');assert current['max_tokens']==1234 and current['models']==MAPPINGS
    assert 'TEST_ONLY_NOT_A_REAL_KEY' not in (tmp_path/'opencode.json').read_text()
    assert list(tmp_path.glob('opencode.json.bak-*'))

def test_modified_provider_is_not_overwritten(tmp_path):
    cfg={'providers':{'fkg-glm':{'name':'user changed'}}};path=tmp_path/'opencode.json';path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='merge manually'):configure(tmp_path)
    assert load(path)==cfg

def test_agent_regeneration_preserves_providers(tmp_path):
    spec=importlib.util.spec_from_file_location('configure_agent_test',ROOT/'scripts/configure_opencode.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=tmp_path/'opencode.json';module.configure(output)
    cfg=load(output);cfg['providers']=copy.deepcopy(PROVIDERS);output.write_text(json.dumps(cfg))
    module.configure(output)
    assert load(output)['providers']==PROVIDERS
