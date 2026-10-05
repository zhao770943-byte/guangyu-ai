"""Read-only metadata triage. No generation, approvals or credential access."""
import argparse
import json
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ACTIVE = {'queued','running','pending','processing','saving'}
MAX_BYTES = 16 * 1024 * 1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Local API redirects are not followed.')

def read_project(args):
    if args.file:
        path=Path(args.file)
        if path.stat().st_size>MAX_BYTES:raise ValueError('Project file exceeds 16 MiB.')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    base=urllib.parse.urlsplit(args.base_url)
    if base.scheme not in ('http','https') or base.hostname not in ('127.0.0.1','localhost','::1') or base.username or base.password or base.query or base.fragment or base.path not in ('','/'):
        raise ValueError('Use a loopback API origin without credentials or path.')
    if not re.fullmatch('[a-f0-9]{32}', args.project_id or ''):
        raise ValueError('A 32-character project ID is required.')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(args.base_url.rstrip('/')+'/api/novels?id='+args.project_id, timeout=20) as result:
        raw=result.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Project response exceeds 16 MiB.')
    return json.loads(raw)

def audit(p):
    if not isinstance(p,dict):raise ValueError('Expected a project object.')
    state=p.get('production_state') or {}
    book=p.get('production_book') or {}
    issues=[]
    def add(code,slot='',severity='block'):
        issues.append({'code':code,'slot':slot,'severity':severity})
    episodes=(p.get('plan') or {}).get('episodes',[])
    shots=[('shot:'+e['id']+':'+s['id'],s) for e in episodes for s in e.get('shots',[])]
    if not episodes:add('script_missing')
    if not state.get('enabled',book.get('enabled',False)):add('legacy_flow_no_version_gate',severity='review')
    dialogue={}
    for key,s in shots:
        if not p.get('images',{}).get(key):add('storyboard_missing',key)
        if state.get('shots',{}).get(key,{}).get('status')!='approved':add('storyboard_current_version_not_approved',key)
        c=book.get('contracts',{}).get(key,{})
        if any(not isinstance(c.get(k),str) or not c[k].strip() for k in ('start','end','eyeline','crowd','bridge','beats','avoid')):add('staging_contract_incomplete',key)
        if c.get('sound_mode') not in ('dub','native','silent'):add('sound_mode_unset',key)
        for aid in s.get('asset_ids',[]):
            if not p.get('locked_assets',{}).get(aid):add('master_reference_unlocked',key)
        line=s.get('dialogue','').strip()
        if line:
            if line in dialogue:add('repeated_dialogue_check',key,'review')
            dialogue[line]=key
    for issue in book.get('issues',[]):
        if not issue.get('resolved'):add('open_production_issue',issue.get('shot',''))
    jobs=p.get('jobs') or []
    failures=sum(j.get('status')=='failed' for j in jobs)
    if failures:add('failed_jobs_query_original_before_retry',severity='review')
    if p.get('phase')=='complete' and not state.get('delivery_approved'):add('final_listen_and_watch_not_recorded',severity='review')
    return {'format':'guangyu-audit-v1','project_id':p.get('id'),'project_version':p.get('version'),
            'phase':p.get('phase'),'paused':p.get('paused'),'episodes':len(episodes),'shots':len(shots),
            'approved_storyboards':sum(v.get('status')=='approved' for v in state.get('shots',{}).values()),
            'jobs_active':sum(j.get('status') in ACTIVE for j in jobs),'jobs_failed':failures,
            'requests_used':p.get('requests_used',0),'request_limit':p.get('request_limit'),
            'delivery_record_current':bool(state.get('delivery_approved')),
            'issues':issues,'metadata_blockers':sum(i['severity']=='block' for i in issues),
            'actual_picture_audio_review':'not_performed_by_this_script'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--file')
    source.add_argument('--base-url')
    parser.add_argument('--project-id')
    parser.add_argument('--output')
    args=parser.parse_args()
    try:
        report=audit(read_project(args))
        result=json.dumps(report,ensure_ascii=False,indent=2)
        if args.output:Path(args.output).write_text(result+'\n',encoding='utf-8')
        print(result)
        return 2 if report['metadata_blockers'] else 0
    except (ValueError,OSError,KeyError,TypeError):
        print('Cannot audit project: invalid input or local service unavailable. No project changes made.',file=sys.stderr)
        return 1
if __name__=='__main__':sys.exit(main())
