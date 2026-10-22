import os,subprocess,shutil
from pathlib import Path
root=Path.cwd();evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');home=root/'.test-phase-tmp/launcher-lab';child=None
log=(evidence/'live-launcher-transcript.log').open('w',buffering=1)
env={k:v for k,v in os.environ.items() if not k.startswith('FM_')};env.update(FM_HOME=str(home),TMPDIR=str(root/'.test-phase-tmp/tmp'),LC_ALL='C',TZ='Europe/Berlin')
def run(args,rc=0):
    r=subprocess.run(list(map(str,args)),env=env,capture_output=True,text=True,timeout=45)
    print('$ '+' '.join(map(str,args)),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True);assert r.returncode==rc,r
    return r
try:
    run([root/'bin/fm-lab-home.sh','create',home]);child=subprocess.Popen(['/bin/sleep','300'],env=env)
    lock=home/'state/.afk-launch.lock';lock.mkdir();(lock/'pid').write_text(str(child.pid))
    identity=lock/'pid-identity';original=run(['bash','-c','. "$1"; fm_pid_identity "$2"','_',root/'bin/fm-wake-lib.sh',child.pid]).stdout.strip()
    (home/'state/.wake-queue').write_text('retained feedback\n')
    for kind in ['legacy','malformed','empty','missing']:
        if kind=='legacy':identity.write_text(original.removeprefix('ps-utc-v1=')+'\n')
        elif kind=='malformed':identity.write_text('unknown identity\n')
        elif kind=='empty':identity.write_text('')
        else:identity.unlink()
        before={str(p.relative_to(home/'state')):p.read_bytes() for p in (home/'state').rglob('*') if p.is_file()}
        r=run([root/'bin/fm-afk-launch.sh','--help'],rc=1)
        assert 'live launcher identity is unverifiable' in r.stderr
        after={str(p.relative_to(home/'state')):p.read_bytes() for p in (home/'state').rglob('*') if p.is_file()}
        assert before==after and child.poll() is None
        print('OBSERVED: '+kind+' live launcher claim refuses acquisition and remains byte-identical',file=log)
    identity.write_text(original+' different-command\n');run([root/'bin/fm-afk-launch.sh','--help']);assert not lock.exists() and child.poll() is None
    print('OBSERVED: a proven stable mismatch can be reclaimed without signalling the unrelated live process\nPASS',file=log)
finally:
    if child and child.poll() is None:child.terminate();child.wait(timeout=10)
    if home.exists():shutil.rmtree(home)
    log.close()
