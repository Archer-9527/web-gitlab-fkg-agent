"""Experiment client; API credentials remain in server/OpenCode environment."""
import argparse,json,httpx
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');s=p.add_subparsers(dest='command',required=True)
a=s.add_parser('start');a.add_argument('--source15',required=True);a.add_argument('--source17',required=True)
s.add_parser('status');a=s.add_parser('compare');a.add_argument('left');a.add_argument('right')
a=p.parse_args()
with httpx.Client(base_url=a.url,timeout=60,trust_env=False) as c:
 if a.command=='start':r=c.post('/api/experiments',json={'source15':a.source15,'source17':a.source17})
 elif a.command=='status':r=c.get('/api/experiments')
 else:r=c.post('/api/compare',json={'left':a.left,'right':a.right})
 r.raise_for_status();print(json.dumps(r.json(),ensure_ascii=False,indent=2))
