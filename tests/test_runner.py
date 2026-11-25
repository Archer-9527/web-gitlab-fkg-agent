import json
from copy import deepcopy
import httpx,pytest
from app.runner import OpenCodeRunner,Connection,RunnerError,RunnerTimeout,RunnerCancelled,parse_sse
from app.common import ROOT,load

MODEL={'id':'actual-ds-id','providerID':'gateway-ds'}
def transport_handler(request):
    path=request.url.path
    if path=='/api/info':return httpx.Response(200,json={'version':'2.0.32'})
    if path=='/openapi.json':return httpx.Response(200,json=load(ROOT/'docs/upstream/opencode-v2.0.32.openapi.json'))
    if path=='/api/agent':
        assert request.url.params['location[directory]']=='/project'
        return httpx.Response(200,json={'location':{'directory':'/project'},'data':[{'id':'gitlab-fkg'}]})
    if path=='/api/mcp':return httpx.Response(200,json={'data':[{'name':'fkg','status':{'status':'connected'}}]})
    if path=='/api/model':return httpx.Response(200,json={'data':[dict(MODEL,name='test')]})
    if path=='/api/session' and request.method=='POST':
        body=json.loads(request.content);assert body['model']==MODEL;assert body['agent']=='gitlab-fkg';assert body['location']=={'directory':'/project'}
        return httpx.Response(200,json={'data':{'id':'ses_test'}})
    if path.endswith('/prompt'):
        body=json.loads(request.content);assert body=={'id':'msg_stable','text':'read original','resume':True};return httpx.Response(200,json={'data':{'id':'inbox'}})
    if path.endswith('/interrupt'):return httpx.Response(200,json={'interrupted':True})
    if path.endswith('/message'):
        return httpx.Response(200,json={'data':[{'id':'msg_result','type':'assistant','agent':'gitlab-fkg','model':MODEL,'content':[{'type':'text','text':'{"artifact_id":"a"}'},{'type':'reasoning','text':'NEVER_LOG_REASONING'},{'type':'tool','id':'t','name':'fkg_read','state':{'status':'completed'}}]}],'cursor':{}})
    if path=='/api/session/ses_test':return httpx.Response(200,json={'data':{'id':'ses_test','model':MODEL,'agent':'gitlab-fkg','outcome':'succeeded','tokens':{'input':5,'output':3},'cost':0.1}})
    return httpx.Response(404,json={})

@pytest.fixture
def runner():return OpenCodeRunner(Connection(directory='/project',poll_seconds=0),httpx.MockTransport(transport_handler))

def test_connection_agent_models(runner):
    assert runner.check()['agent_available'];assert runner.models()[0]['id']=='actual-ds-id'
def test_create_submit_parse_result_and_reasoning_filtered(runner):
    assert runner.create('run',MODEL)['id']=='ses_test';runner.submit('ses_test','msg_stable','read original')
    result=runner.poll('ses_test',MODEL);assert result['tokens']['input']==5;assert 'NEVER_LOG_REASONING' not in json.dumps(result['messages'])
def test_model_mapping_actually_checked(runner):
    with pytest.raises(RunnerError,match='differs'):runner.poll('ses_test',{'id':'glm-id','providerID':'gateway-glm'})
def test_budget_includes_usage(runner):
    with pytest.raises(RunnerError,match='budget'):runner.poll('ses_test',MODEL,budget={'max_tokens':7})
def test_cancel(runner):
    with pytest.raises(RunnerCancelled):runner.poll('ses_test',MODEL,cancelled=lambda:True)
def test_disconnect():
    def fail(req):raise httpx.ConnectError('offline')
    r=OpenCodeRunner(Connection(),httpx.MockTransport(fail))
    with pytest.raises(RunnerError,match='disconnected'):r.check()
def test_transport_timeout():
    def fail(req):raise httpx.ReadTimeout('timeout')
    r=OpenCodeRunner(Connection(),httpx.MockTransport(fail))
    with pytest.raises(RunnerTimeout):r.check()
def test_task_timeout():
    def pending(req):
        if req.url.path=='/api/session/ses_test':return httpx.Response(200,json={'data':{'id':'ses_test'}})
        return transport_handler(req)
    r=OpenCodeRunner(Connection(timeout=0,poll_seconds=0),httpx.MockTransport(pending))
    with pytest.raises(RunnerTimeout,match='checkpoint'):r.poll('ses_test',MODEL)
def test_no_silent_version_fallback():
    def changed(req):return httpx.Response(200,json={'version':'2.0.33'})
    r=OpenCodeRunner(Connection(),httpx.MockTransport(changed))
    with pytest.raises(RunnerError,match='Unsupported'):r.check()
def test_sse_multiline_and_nested_json():
    events=list(parse_sse(':keepalive\r\nid: 12\r\nevent: upstream-name\r\ndata: {"seq":12,\r\ndata: "type":"observed"}\r\n\r\n'))
    assert events==[{'id':'12','event':'upstream-name','data':{'seq':12,'type':'observed'}}]
def test_requests_match_actual_openapi(runner):
    from jsonschema import Draft202012Validator
    spec=load(ROOT/'docs/upstream/opencode-v2.0.32.openapi.json');base=spec['paths']['/api/session']['post']['requestBody']['content']['application/json']['schema']
    schema=dict(base,components=spec['components'])
    assert not list(Draft202012Validator(schema).iter_errors({'agent':'gitlab-fkg','model':MODEL,'location':{'directory':'/project'}}))
    wrong={'agent':'gitlab-fkg','model':{'providerID':'x','modelID':'old-v1-field'},'directory':'/project'}
    assert list(Draft202012Validator(schema).iter_errors(wrong))
