import os, pathlib, subprocess, json, hashlib
root=pathlib.Path.cwd()
evidence=pathlib.Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M67568PPD081WGPMF7D84276')
work=root/'.test-quiet'
basebin=work/'baseline-bin'; basebin.mkdir(exist_ok=True)
for p in (root/'bin').iterdir():
    if not (basebin/p.name).exists(): (basebin/p.name).symlink_to(p)
(basebin/'fm-afk-return.sh').unlink()
(basebin/'fm-afk-return.sh').write_bytes(subprocess.check_output(['git','show','83b70ef49e33eff529f574618415997c8ef67518:bin/fm-afk-return.sh']))
(basebin/'fm-afk-return.sh').chmod(0o755)
log=[]; results=[]
def run(home,args,extra=None):
    env={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_'))}
    env.update(FM_HOME=str(home),FM_ROOT_OVERRIDE=str(home),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_CONFIG_OVERRIDE=str(home/'config'),FM_PROJECTS_OVERRIDE=str(home/'projects'),TMPDIR=str(work/'tmp'))
    if extra: env.update(extra)
    p=subprocess.run(args,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    log.append({'home':str(home),'command':args,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    return p

def state(home):
    return {str(p.relative_to(home)):hashlib.sha256(p.read_bytes()).hexdigest() for p in home.rglob('*') if p.is_file()}

cases=[('none',None,None,False,0),('quiet-record','quiet',None,False,0),('quiet-flag',None,'quiet\n123\n',False,0),('quiet-both','quiet','quiet\n123\n',False,0),('away-record','away',None,False,3),('away-flag',None,'away\n123\n',False,3),('legacy-flag',None,'123\n',False,3),('empty-flag',None,'',False,3),('unknown-flag',None,'unknown\n',False,3),('malformed-record','malformed',None,False,3),('quiet-flag-away-record','away','quiet\n123\n',False,3),('away-flag-quiet-record','quiet','away\n123\n',False,3),('catchup',None,None,True,4),('quiet-catchup','quiet','quiet\n123\n',True,4)]
for name,mode,flag,catchup,expected in cases:
    home=work/'live-homes'/name
    for sub in ('state','data','config','projects'): (home/sub).mkdir(parents=True,exist_ok=True)
    (home/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 10\n')
    (home/'data/backlog.md').write_text('## In flight\n\n## Queued\n- [ ] quiet-status-example - Review requested status (repo: sample) (kind: scout) (since 2026-10-30)\n\n## Done\n')
    if mode=='malformed': (home/'state/.afk-contract').write_text('version: 2\n')
    elif mode:
        p=run(home,['bash',str(root/'bin/fm-afk-contract.sh'),'enter','--words','Keep the current supervision preference.'],{'FM_AFK_MODE':mode})
        assert p.returncode==0, p.stderr
    if flag is not None: (home/'state/.afk').write_text(flag)
    if catchup: (home/'state/.afk-return-catchup').write_text('evidence\tlifecycle\tretained return evidence\n')
    before=state(home)
    guard=run(home,['bash',str(root/'bin/fm-afk-return.sh'),'guard'])
    report=run(home,['bash',str(root/'bin/fm-bearings-snapshot.sh'),'--json'])
    expected_report=0 if expected==4 else expected
    checks={'guard_exit':guard.returncode==expected,'report_exit':report.returncode==expected_report,'home_unchanged':before==state(home)}
    if report.returncode==0:
        data=json.loads(report.stdout)
        checks['catchup_visible']=('(return-catchup)' in report.stdout)==catchup
        checks['queued_work_visible']='quiet-status-example' in report.stdout
        (evidence/(name+'.json')).write_text(report.stdout)
    if name=='quiet-both':
        toon=run(home,['bash',str(root/'bin/fm-bearings-snapshot.sh')]); checks['default_status']=toon.returncode==0 and 'quiet-status-example' in toon.stdout
        (evidence/'quiet-status.toon').write_text(toon.stdout)
        old=run(home,['bash',str(basebin/'fm-afk-return.sh'),'guard'])
        checks['base_reproduces_bug']=old.returncode==3
        checks['posture_preserved_after_repeated_reads']=before==state(home)
        (evidence/'quiet-posture-before-after.json').write_text(json.dumps({'before':before,'after':state(home)},indent=2))
    results.append({'scenario':name,'pass':all(checks.values()),'checks':checks,'guard_exit':guard.returncode,'report_exit':report.returncode})
    print(json.dumps(results[-1]),flush=True)
absent=work/'absent-home'
p=run(absent,['bash',str(root/'bin/fm-afk-return.sh'),'guard'])
results.append({'scenario':'absent-home','pass':p.returncode==0 and not absent.exists(),'guard_exit':p.returncode})
(evidence/'live-cli-transcript.json').write_text(json.dumps(log,indent=2))
(evidence/'live-scenarios.json').write_text(json.dumps(results,indent=2))
assert all(x['pass'] for x in results), results
