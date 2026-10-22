import os,subprocess,time,shutil,signal
from pathlib import Path
root=Path.cwd();evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');home=root/'.test-phase-tmp/reclaim-lab';children=[]
log=(evidence/'live-reclaim-transcript.log').open('w',buffering=1)
env={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['HERDR_SESSION','HERDR_ENV']};env.update(FM_HOME=str(home),FM_PROCEVENT_CLAIM_ROOT=str(home/'claims'),TMPDIR=str(root/'.test-phase-tmp/tmp'),LC_ALL='C',TZ='Europe/Berlin')
def run(args):
    r=subprocess.run(list(map(str,args)),env=env,capture_output=True,text=True,timeout=35)
    print('$ '+' '.join(map(str,args)),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True);assert r.returncode==0,r
    return r
try:
    run([root/'bin/fm-lab-home.sh','create',home]);claims=home/'claims';claims.mkdir(mode=0o700)
    blocker=home/'blocker.sh';marker=home/'started';release=home/'release'
    blocker.write_text('#!/bin/bash\nprintf "started\\n" >> "$1"\nwhile [ ! -e "$2" ]; do sleep 0.05; done\nprintf "race result\\n"\n');blocker.chmod(0o700)
    run([root/'bin/fm-procevent.sh','register','lavish','reclaim-source','--',blocker,marker,release])
    dead=subprocess.Popen(['true']);dead.wait()
    claim=claims/'reclaim-source.claim';claim.write_text(str(home/'gone-home')+'\n'+str(dead.pid)+'\nold-token\nold-identity\n');claim.chmod(0o600)
    streams=[]
    for n in range(24):
        stream=(evidence/('reclaim-contender-%02d.log'%n)).open('w');streams.append(stream)
        children.append(subprocess.Popen([str(root/'bin/fm-procevent.sh'),'start','reclaim-source'],env=env,stdout=stream,stderr=subprocess.STDOUT))
    deadline=time.monotonic()+35
    while time.monotonic()<deadline and not marker.exists():time.sleep(.1)
    assert marker.exists(),'no contender acquired the known-dead claim within 35s'
    time.sleep(.5);assert marker.read_text().splitlines()==['started']
    print('OBSERVED: 24 concurrent public starts reclaim known-dead PID='+str(dead.pid)+' exactly once; marker='+repr(marker.read_text()),file=log)
    release.touch()
    exits=[p.wait(timeout=35) for p in children]
    print('Contender exits='+repr(exits),file=log);assert all(rc==0 for rc in exits),exits
    outputs=list((home/'state/procevent-inbox').glob('*.result'));assert len(outputs)>=1
    print('Captured results after releasing the winner='+str(len(outputs))+' (later sequential starts are allowed)',file=log)
    for output in outputs:print(output.name+'='+output.read_text(),file=log)
    run([root/'bin/fm-procevent.sh','retire','reclaim-source']);print('PASS',file=log)
finally:
    if home.exists():(home/'release').touch()
    for p in children:
        if p.poll() is None:p.terminate()
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    if home.exists():shutil.rmtree(home)
    log.close()
