"""Generate project-local OpenCode v2 configuration without touching global/provider configuration."""
import argparse,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def configure(output=None,refresh=False):
    output=Path(output or root/'opencode.json')
    if output.exists():
        existing=json.loads(output.read_text(encoding='utf-8-sig'))
        if set(existing)-{'agents','mcp','share','snapshots','update','policies','providers'} or set(existing.get('agents',{}))-{'gitlab-fkg'} or set(existing.get('mcp',{}).get('servers',{}))-{'fkg'}:
            raise SystemExit('Existing user configuration detected; merge config/opencode.v2.example.json manually instead of overwriting.')
    cfg={'share':'disabled','snapshots':False,'update':'disable',
         'agents':{'gitlab-fkg':{'description':'Version-pinned manual understanding, semantic extraction and incremental FKG updates', 'mode':'primary','steps':60,'permissions':[{'action':'*','resource':'*','effect':'deny'},{'action':'fkg_*','resource':'*','effect':'allow'}],
                               'system':(root/'instructions/gitlab-fkg.md').read_text(encoding='utf-8-sig')}},
         'mcp':{'servers':{'fkg':{'type':'local','codemode':False,'command':[sys.executable,'-m','app.tools'],'cwd':str(root),
                    'environment':{'PYTHONUTF8':'1','FKG_DATA_DIR':str(root/'data')},'timeout':{'startup':30000,'catalog':30000,'execution':60000}}}}}
    if output.exists() and 'providers' in existing:
        cfg['providers']=existing['providers']
    if output.exists() and existing!=cfg:
        if not refresh:raise SystemExit('Project config differs. Inspect it and use --refresh to preserve a backup and regenerate, or merge manually.')
        import hashlib
        backup=output.with_suffix('.json.bak-'+hashlib.sha256(output.read_bytes()).hexdigest()[:12])
        if not backup.exists():backup.write_bytes(output.read_bytes())
    output.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');print('Wrote project-local config:',output)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--refresh',action='store_true');a=p.parse_args();configure(a.output,a.refresh)
