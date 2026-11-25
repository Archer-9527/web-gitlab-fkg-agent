from __future__ import annotations
import threading
from .common import uid,now

class Imports:
    def __init__(self,store,docs):
        self.store=store;self.docs=docs
        for job in store.list('import'):
            if job['status']=='running':job.update(status='checkpointed',error='Application restarted; resume verified download cache');store.put('import',job)
    def start(self,version,id=None):
        if version not in {'15.0','17.0'}:raise ValueError('formal versions: 15.0, 17.0')
        if id:
            job=self.store.get('import',id)
            if job['status']=='running':raise ValueError('import already running')
            job.update(status='running',error=None)
        else:job={'id':uid('import'),'version':version,'status':'running','created_at':now(),'stage':'verify_tag','processed':0,'total':None}
        self.store.put('import',job);threading.Thread(target=self.execute,args=(job,),daemon=True).start();return job
    def execute(self,job):
        def progress(stage,processed,total):
            job.update(stage=stage,processed=processed,total=total);self.store.put('import',job)
        try:
            s=self.docs.official(job['version'],progress=progress,import_id=job['id']);failed=sum(d['processing_status']=='failed' for d in s['documents']);job.update(status='checkpointed' if failed else 'succeeded',source_id=s['id'],error=f'{failed} failed files; resume retries missing downloads' if failed else None)
        except Exception as exc:job.update(status='checkpointed',error=type(exc).__name__+': '+str(exc).split('?')[0])
        job['ended_at']=now();self.store.put('import',job)
