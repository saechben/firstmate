import os, pathlib, subprocess, tempfile, shutil, json, hashlib, re
root=pathlib.Path.cwd()
ev=pathlib.Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M67568PPD081WGPMF7D84276')
work=root/'.test-quiet-live'
work.mkdir(exist_ok=False)
log=(ev/'round2-live-cli.log').open('w')
results=[]
env0={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_','TMUX','HERDR')) and k not in ('STATE','DATA','CONFIG')}
env0.update(TMPDIR=str(work), GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')
def emit(s):
    log.write(s+'\n'); log.flush()
def run(home, script, *args, expect=0, extra=None, readonly=False):
    env=dict(env0,FM_HOME=str(home),HOME=str(home))
    if extra: env.update(extra)
    cmd=['/bin/bash',str(root/'bin'/script),*args]
    emit('$ FM_HOME='+str(home)+' '+' '.join(cmd)+(' [stdout=open(O_RDONLY)]' if readonly else ''))
    if readonly:
        sink=home/'read-only-output'; sink.touch()
        with sink.open('r') as f: p=subprocess.run(cmd,env=env,text=True,stdout=f,stderr=subprocess.PIPE,timeout=60)
        stdout=''
    else:
        p=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=60); stdout=p.stdout
    emit(stdout+p.stderr+'\nexit='+str(p.returncode))
    if expect is not None: assert p.returncode==expect,(script,args,p.returncode,expect,stdout,p.stderr)
    return stdout,p.stderr,p.returncode

def home(name):
    h=work/name
    run(h,'fm-lab-home.sh','create',str(h))
    (h/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 10\n')
    (h/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n- [ ] lab-status - Read-only status fixture (repo: sample) (kind: ship) (since 2026-10-30)\n\n## Done\n')
    (h/'config/supervision-host-off').touch()
    return h

def snap(h):
    return {str(p.relative_to(h)):hashlib.sha256(p.read_bytes()).hexdigest() for p in h.rglob('*') if p.is_file()}
def record(h,mode):
    run(h,'fm-afk-contract.sh','enter','--words','Keep quiet supervision enabled',extra={'FM_AFK_MODE':mode})
def result(name):
    results.append({'name':name,'result':'pass','live':True}); emit('PASS '+name)
try:
    emit(subprocess.check_output(['/bin/bash','--version'],text=True).splitlines()[0])
    for case in ['none','quiet-record','quiet-flag','quiet-both','away-record','away-flag','legacy-flag','empty-flag','unknown-flag','malformed-record','quiet-flag-away-record','away-flag-quiet-record','catchup','quiet-catchup']:
        h=home(case); state=h/'state'
        if case in ['quiet-record','quiet-both','away-flag-quiet-record','quiet-catchup']: record(h,'quiet')
        if case in ['away-record','quiet-flag-away-record']: record(h,'away')
        if case=='malformed-record': (state/'.afk-contract').write_text('version: 2\n')
        flags={'quiet-flag':'quiet\n123\n','quiet-both':'quiet\n123\n','quiet-flag-away-record':'quiet\n123\n','quiet-catchup':'quiet\n123\n','away-flag':'away\n123\n','away-flag-quiet-record':'away\n123\n','legacy-flag':'123\n','empty-flag':'','unknown-flag':'unknown\n'}
        if case in flags: (state/'.afk').write_text(flags[case])
        if 'catchup' in case: (state/'.afk-return-catchup').write_text('evidence\tlifecycle\tPending recovery fixture\n')
        before=snap(h)
        expected=0 if case in ['none','quiet-record','quiet-flag','quiet-both'] else 4 if 'catchup' in case else 3
        run(h,'fm-afk-return.sh','guard',expect=expected)
        assert snap(h)==before,'guard mutated home '+case
        out,_,_=run(h,'fm-bearings-snapshot.sh','--json',expect=0 if expected==4 else expected)
        if expected in (0,4):
            obj=json.loads(out)
            assert any(g['id']=='lab-status' for g in obj['gates']),obj
            rows=[g for g in obj['gates'] if g['id']=='(return-catchup)']
            assert bool(rows)==(expected==4),obj
            if rows: assert not rows[0].get('action'),rows
        after=snap(h)
        assert {k:v for k,v in after.items() if k.startswith('state/')}=={k:v for k,v in before.items() if k.startswith('state/')},'snapshot mutated posture '+case
        emit('State SHA256 manifest unchanged: '+json.dumps({k:v for k,v in after.items() if k.startswith('state/')},sort_keys=True))
        if case=='quiet-both':
            run(h,'fm-bearings-snapshot.sh')
            baseline=root/'bin/.test-quiet-baseline.sh'
            baseline.write_bytes(subprocess.check_output(['git','show','83b70ef49e33eff529f574618415997c8ef67518:bin/fm-afk-return.sh']))
            try: run(h,baseline.name,'guard',expect=3)
            finally: baseline.unlink()
        result(case)
    absent=work/'absent'
    run(absent,'fm-afk-return.sh','guard')
    assert not absent.exists()
    result('absent-home guard creates nothing')
    h=home('quiet-off'); record(h,'quiet'); (h/'state/.afk').write_text('quiet\n123\n')
    epoch=run(h,'fm-afk-contract.sh','field','entered_epoch')[0].strip()
    run(h,'fm-afk-return.sh','begin')
    assert not (h/'state/.afk').exists() and not (h/'state/.afk-contract').exists()
    assert (h/f'state/afk-contracts/{epoch}.afk-contract').is_file()
    run(h,'fm-afk-return.sh','guard')
    result('explicit quiet off archives posture and clears gate')
    h=home('publication-retry')
    # Append through the production durable queue API, then run the real return and drain commands.
    cmd=['/bin/bash','-c','. bin/fm-wake-lib.sh; fm_wake_append check lab-recovery "check: recover after output failure"']
    emit('$ '+ ' '.join(cmd))
    p=subprocess.run(cmd,env=dict(env0,FM_HOME=str(h),HOME=str(h)),text=True,capture_output=True,timeout=60)
    emit(p.stdout+p.stderr+'exit='+str(p.returncode)); assert p.returncode==0
    queue=h/'state/.wake-queue'; queued=queue.read_text(); emit('Queued before failure:\n'+queued)
    run(h,'fm-afk-return.sh','begin',readonly=True,expect=3)
    assert queue.read_text()==queued,'wake lost on failed output'
    gate=h/'state/.afk-return-catchup'
    assert gate.is_file() and 'return brief publication failed' in gate.read_text()
    emit('Retained catch-up gate:\n'+gate.read_text())
    run(h,'fm-afk-return.sh','guard',expect=4)
    out,err,_=run(h,'fm-afk-return.sh','check')
    assert 'check: recover after output failure' in out and 'WAKE_ACK_REQUIRED:' in out+err
    assert queue.read_text()==queued and not gate.exists()
    out,err,_=run(h,'fm-afk-return.sh','check')
    assert 'check: recover after output failure' in out
    match=re.search(r'--ack-through (\d+) --recovery-generation ([A-Za-z0-9._-]+)',out+err); assert match
    run(h,'fm-wake-drain.sh','--ack-through',match[1],'--recovery-generation',match[2])
    assert not queue.read_text().strip()
    assert not list((h/'state').glob('.afk-return-brief.*'))
    emit('After handling acknowledgement: durable queue empty; catch-up cleared; no brief scratch files.')
    result('read-only stdout retains wake and catch-up; retry replays until acknowledged')
finally:
    shutil.rmtree(work)
    emit('All disposable live homes removed.')
    (ev/'round2-live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    log.close()
