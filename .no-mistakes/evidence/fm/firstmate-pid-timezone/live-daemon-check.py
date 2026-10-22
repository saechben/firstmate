import os, subprocess, time, threading, shutil
from pathlib import Path
root=Path.cwd(); evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J')
home=root/'.test-phase-tmp/daemon-lab'; daemon=None
log=(evidence/'live-daemon-transcript.log').open('w',buffering=1)
def say(s): print(s, file=log, flush=True)
env={k:v for k,v in os.environ.items() if k not in ['FM_ROOT_OVERRIDE','FM_STATE_OVERRIDE','FM_DATA_OVERRIDE','FM_CONFIG_OVERRIDE','FM_PROJECTS_OVERRIDE','FM_GATE_REFUSE_BYPASS','FM_AFK_LAUNCH_ENTRY','HERDR_SESSION','HERDR_ENV','PI_CODING_AGENT','FM_PI_HARNESS']}
env.update(FM_HOME=str(home),TMPDIR=str(root/'.test-phase-tmp/tmp'),FM_TEST_HARNESS='claude',FM_TEST_SEAM='1',CLAUDECODE='1',TMUX='.test-phase-tmp/lab.sock,0,0',TMUX_PANE='%0',FM_SUPERVISOR_BACKEND='tmux',FM_SUPERVISOR_TARGET='fm-lab-primary:0.0',FM_HEARTBEAT='999999',FM_CHECK_INTERVAL='999999',FM_POLL='1',FM_WEDGE_ALARM_EXEC='discard')
def run(argv, expected=0, zone='Europe/Berlin'):
    r=subprocess.run(list(map(str,argv)),env=dict(env,TZ=zone),text=True,capture_output=True,timeout=90)
    say('$ '+' '.join(map(str,argv))+' [TZ='+zone+']');say(r.stdout+r.stderr);say('exit='+str(r.returncode))
    if expected is not None: assert r.returncode==expected, r
    return r
launch=root/'bin/fm-afk-launch.sh'; start=root/'bin/fm-afk-start.sh'
def snapshot():
    return {str(p.relative_to(home/'state')):p.read_bytes() for p in (home/'state').rglob('*') if p.is_file() and (p.name in ['.afk','.afk-contract','.afk-daemon-terminal','.subsuper-escalations'] or '.supervise-daemon.lock' in str(p))}
try:
    run([root/'bin/fm-lab-home.sh','create',home]);(home/'config/supervision-host-off').touch()
    run([launch,'enter','--words','disposable validation only'])
    run([launch,'start-native'])
    stream=(evidence/'live-daemon-process.log').open('w')
    daemon=subprocess.Popen([str(start)],env=env,stdout=stream,stderr=subprocess.STDOUT)
    identity=home/'state/.supervise-daemon.lock/pid-identity'
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if identity.exists() and identity.stat().st_size and (home/'state/.supervise-daemon.log').exists() and 'daemon starting' in (home/'state/.supervise-daemon.log').read_text(): break
        assert daemon.poll() is None, 'real daemon exited at startup'
        time.sleep(.05)
    else: raise AssertionError('real daemon did not start')
    original=identity.read_bytes();say('Actual daemon PID='+str(daemon.pid)+' identity='+original.decode().strip())
    for zone in ['America/Argentina/Buenos_Aires','Europe/Berlin']:
        run([launch,'start-native'],zone=zone)
        assert identity.read_bytes()==original
    say('OBSERVED: actual daemon recognized across timezone changes without replacement')
    for kind in ['missing','empty']:
        if kind=='missing': identity.unlink()
        else: identity.write_bytes(b'')
        published=[]
        def publish():
            time.sleep(.35);identity.write_bytes(original);published.append(True)
        thread=threading.Thread(target=publish);thread.start();started=time.monotonic()
        r=run(['bash','-c','. "$1"; fm_afk_launch_wait_ready tmux fm-lab-primary:0.0','_',launch])
        elapsed=time.monotonic()-started;thread.join()
        assert published and elapsed>=.3 and daemon.poll() is None
        say('OBSERVED: readiness waited through '+kind+' identity; completed after %.3fs'%elapsed)
    identity.unlink();before=(home/'state/.afk-daemon-terminal').read_bytes();started=time.monotonic()
    run(['bash','-c','. "$1"; fm_afk_launch_commit_terminal none - native 1','_',launch],expected=2)
    elapsed=time.monotonic()-started
    assert elapsed>=4.8 and daemon.poll() is None and (home/'state/.afk-daemon-terminal').read_bytes()==before
    say('OBSERVED: deadline retained actual daemon and terminal record after %.3fs'%elapsed)
    identity.write_bytes(original)
    # Give the real daemon a quiet interval: no signals or queued records are introduced.
    (home/'state/.subsuper-escalations').write_text('retained validation feedback\n')
    for kind in ['legacy','malformed','empty','missing']:
        if kind=='legacy': identity.write_bytes(original.removeprefix(b'ps-utc-v1='))
        elif kind=='malformed': identity.write_bytes(b'unknown identity\n')
        elif kind=='empty': identity.write_bytes(b'')
        else: identity.unlink()
        for action in ['start','start-native','stop','reconcile']:
            saved=snapshot();run([launch,action],expected=2)
            assert daemon.poll() is None and snapshot()==saved,(kind,action)
        say('OBSERVED: '+kind+' actual-daemon identity refused all lifecycle actions and preserved feedback and claims')
        identity.write_bytes(original)
    (home/'state/.subsuper-escalations').unlink()
    run([launch,'stop']);daemon.wait(timeout=15)
    assert not (home/'state/.afk').exists()
    say('OBSERVED: verified stop shuts down actual daemon and clears away flag')
    say('PASS: live daemon timezone, readiness publication/deadline, and ownership-preservation scenarios')
finally:
    if daemon and daemon.poll() is None:
        if 'original' in locals() and identity.parent.exists():identity.write_bytes(original)
        daemon.terminate()
        try: daemon.wait(timeout=15)
        except subprocess.TimeoutExpired:daemon.kill();daemon.wait()
    if home.exists():shutil.rmtree(home)
    log.close()
