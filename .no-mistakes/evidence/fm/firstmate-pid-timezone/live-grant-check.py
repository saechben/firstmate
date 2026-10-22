import os,subprocess,shutil
from pathlib import Path
root=Path.cwd();evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');home=root/'.test-phase-tmp/grant-lab'
log=(evidence/'live-grant-transcript.log').open('w',buffering=1)
env={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['HERDR_SESSION','HERDR_ENV']};env.update(FM_HOME=str(home),TMPDIR=str(root/'.test-phase-tmp/tmp'),TMUX='.test-phase-tmp/lab.sock,0,0',LC_ALL='C',TZ='Europe/Berlin')
def run(argv,actor=None,expected=0):
    r=subprocess.run(list(map(str,argv)),env=dict(env,**({'FM_SUPERVISION_ACTOR':actor} if actor else {})),capture_output=True,text=True,timeout=30)
    print('$ '+' '.join(map(str,argv))+' actor='+str(actor),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True)
    assert r.returncode==expected,r
    return r
try:
    run([root/'bin/fm-lab-home.sh','create',home]);state=home/'state'
    run(['bash','-c','. "$1"; fm_wake_append check disposable "check: retained feedback"','_',root/'bin/fm-wake-lib.sh'])
    grant=root/'bin/fm-wake-grant.sh'
    run([grant,'activate',os.getpid(),'disposable-generation']);run([grant,'publish','disposable-generation','1'])
    owner=state/'.branch-eligible-owner';original=owner.read_bytes();lines=owner.read_text().splitlines();assert lines[2].startswith('ps-utc-v1=');lines[2]=lines[2][len('ps-utc-v1='):];owner.write_text('\n'.join(lines)+'\n')
    files=[state/'.wake-queue',state/'.branch-eligible-rows',owner];saved=[p.read_bytes() for p in files]
    for actor in ['main','branch']:
        r=run([root/'bin/fm-wake-drain.sh'],actor=actor,expected=1)
        assert 'owner identity is unverifiable' in r.stderr
        assert [p.read_bytes() for p in files]==saved
    print('OBSERVED: both actors refuse to consume queued feedback or reclaim an unverifiable live owner grant; all three persisted records are byte-identical',file=log)
    owner.write_bytes(original);run([grant,'release','disposable-generation']);run([grant,'deactivate',os.getpid(),'disposable-generation'])
    print('PASS',file=log)
finally:
    if home.exists():shutil.rmtree(home)
    log.close()
