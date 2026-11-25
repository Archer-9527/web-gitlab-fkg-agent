import httpx,json
from pathlib import Path
from app.documents import PINNED,API
from app.common import sha

def test_official_import_enumerates_all_roots_and_preserves_failed_files(env,monkeypatch):
    store,docs,tmp=env;attempts={'raw':0}
    def handler(req):
        path=req.url.path
        if '/tags/' in path:return httpx.Response(200,json={'commit':{'id':PINNED['15.0']['commit']}})
        if path.endswith('/tree'):
            if req.url.params['page']=='1':return httpx.Response(200,json=[{'type':'blob','path':'doc/user/a.md'},{'type':'blob','path':'doc/ci/b.md'},{'type':'blob','path':'doc/new_product_area/c.md'},{'type':'blob','path':'doc/development/internal.md'}])
            return httpx.Response(200,json=[])
        if '/files/' in path:
            attempts['raw']+=1
            if 'b.md' in path:return httpx.Response(503,json={'error':'outage'})
            return httpx.Response(200,content=b'# Controlled transport fixture\nNot real GitLab facts')
        return httpx.Response(404)
    real=httpx.Client
    monkeypatch.setattr('app.documents.httpx.Client',lambda **kw:real(transport=httpx.MockTransport(handler)))
    progress=[];s=docs.official('15.0',progress=lambda *x:progress.append(x),import_id='import_fixture')
    assert len(s['documents'])==3;assert any(d['processing_status']=='failed' for d in s['documents'])
    assert s['excluded_documents']==[{'path':'doc/development/internal.md','reason':'product engineering, not user operations'}]
    assert s['coverage_status']=='partial';assert any(d['path']=='doc/new_product_area/c.md' for d in s['documents'])
    assert s['commit']==PINNED['15.0']['commit'];before=attempts['raw']
    docs.official('15.0',import_id='import_fixture');assert attempts['raw']==before+1 # retry failed only, verified cached bytes reused
    assert progress[-1]==('snapshot',3,3)
