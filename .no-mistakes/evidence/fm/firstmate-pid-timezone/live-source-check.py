import os, subprocess, time, shutil
from pathlib import Path
root=Path.cwd(); evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');home=root/'.test-phase-tmp/source-lab'
log=(evidence/'live-source-transcript.log').open('w',buffering=1);runner=None;original=None
base={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['HERDR_SESSION','HERDR_ENV','TASKS_AXI_FILE','TASKS_AXI_BACKEND']}
env=dict(base,FM_HOME=str(home),FM_PROCEVENT_CLAIM_ROOT=str(home/'claims'),TMPDIR=str(root/'.test-phase-tmp/tmp'),TMUX='.test-phase-tmp/lab.sock,0,0',LC_ALL='C')
def run(args,zone='America/Argentina/Buenos_Aires',ok=True):
    r=subprocess.run(list(map(str,args)),env=dict(env,TZ=zone),capture_output=True,text=True,timeout=35)
    print('$ TZ='+zone+' '+' '.join(map(str,args)),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True)
    if ok:assert r.returncode==0,r
    return r
def pe(*args,**kwargs):return run([root/'bin/fm-procevent.sh',*args],**kwargs)
try:
    run([root/'bin/fm-lab-home.sh','create',home]);state=home/'state'
    (state/'timezone-worker.meta').write_text('backend=tmux\nwindow=fm-lab-primary:fm-timezone-worker\nproject=disposable\nworktree='+str(root)+'\n')
    pe('register-task','lavish','timezone-source','timezone-worker','--','/bin/sleep','300')
    stream=(evidence/'live-source-process.log').open('w')
    runner=subprocess.Popen([str(root/'bin/fm-procevent.sh'),'start','timezone-source'],env=dict(env,TZ='America/Argentina/Buenos_Aires'),stdout=stream,stderr=subprocess.STDOUT)
    claim=home/'claims/timezone-source.claim';deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if claim.exists() and len(claim.read_text().splitlines())>=4:break
        assert runner.poll() is None,'runner exited'
        time.sleep(.05)
    else:raise AssertionError('runner claim not published')
    original=claim.read_bytes()
    for zone in ['America/Argentina/Buenos_Aires','Europe/Berlin']:
        listed=pe('list',zone=zone);assert 'task:timezone-worker/listening' in listed.stdout
        assert claim.read_bytes()==original
    print('OBSERVED: same real source runner remains listening under both timezones',file=log)
    lines=claim.read_text().splitlines();assert lines[3].startswith('ps-utc-v1=');lines[3]=lines[3][len('ps-utc-v1='):];claim.write_text('\n'.join(lines)+'\n');legacy=claim.read_bytes()
    listed=pe('list',zone='Europe/Berlin');assert 'task:timezone-worker/uncertain' in listed.stdout
    reconciled=pe('reconcile',zone='Europe/Berlin');assert 'started=0' in reconciled.stdout and 'uncertain=1' in reconciled.stdout
    retired=pe('retire','timezone-source',zone='Europe/Berlin',ok=False);assert retired.returncode!=0 and 'cannot confirm runner identity' in retired.stderr
    assert runner.poll() is None and claim.read_bytes()==legacy
    print('OBSERVED: unknown legacy claim stays uncertain, prevents replacement and signalling, and remains byte-identical',file=log)
    claim.write_bytes(original);pe('retire','timezone-source');runner.wait(timeout=12)
    print('OBSERVED: verified fixture source retired through public interface\nPASS',file=log)
finally:
    if original is not None and claim.exists():claim.write_bytes(original)
    if runner and runner.poll() is None:
        pe('retire','timezone-source',ok=False)
        runner.wait(timeout=12)
    if home.exists():shutil.rmtree(home)
    log.close()
