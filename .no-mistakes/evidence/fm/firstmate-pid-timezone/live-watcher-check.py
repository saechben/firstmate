import os, subprocess, time, shutil, signal, threading
from pathlib import Path
root=Path.cwd();evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');home=root/'.test-phase-tmp/watcher-lab';watch=None;original=None
log=(evidence/'live-watcher-transcript.log').open('w',buffering=1)
env={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['HERDR_SESSION','HERDR_ENV','TASKS_AXI_FILE','TASKS_AXI_BACKEND']}
env.update(FM_HOME=str(home),TMPDIR=str(root/'.test-phase-tmp/tmp'),TMUX='.test-phase-tmp/lab.sock,0,0',FM_POLL='1',FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',LC_ALL='C')
def run(args,expected=0,zone='Europe/Berlin'):
    r=subprocess.run(list(map(str,args)),env=dict(env,TZ=zone),capture_output=True,text=True,timeout=30)
    print('$ TZ='+zone+' '+' '.join(map(str,args)),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True)
    if expected is not None:assert r.returncode==expected,r
    return r
try:
    run([root/'bin/fm-lab-home.sh','create',home]);(home/'config/supervision-host-off').touch()
    stream=(evidence/'live-watcher-process.log').open('w')
    watch=subprocess.Popen([str(root/'bin/fm-watch.sh')],env=dict(env,TZ='America/Argentina/Buenos_Aires'),stdout=stream,stderr=subprocess.STDOUT)
    state=home/'state';lock=state/'.watch.lock';identity=lock/'pid-identity';deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if identity.exists() and identity.stat().st_size and (state/'.last-watcher-beat').exists():break
        assert watch.poll() is None,'watcher exited during startup'
        time.sleep(.05)
    else:raise AssertionError('watcher not ready')
    original=identity.read_bytes();print('Actual watcher PID='+str(watch.pid)+' identity='+original.decode(),file=log)
    raw=[]
    for zone in ['America/Argentina/Buenos_Aires','Europe/Berlin']:
        raw.append(run(['ps','-p',str(watch.pid),'-o','lstart='],zone=zone).stdout)
        run(['bash','-c','. "$1"; fm_watcher_healthy "$STATE" "$2" 300 "$FM_HOME"','_',root/'bin/fm-wake-lib.sh',root/'bin/fm-watch.sh'],zone=zone)
    assert raw[0]!=raw[1];print('OBSERVED: raw ps start changes by timezone; actual watcher remains healthy',file=log)
    # Stop only our owned watcher to retain an adversarial stale, live owner.
    os.kill(watch.pid,signal.SIGSTOP)
    (state/'.wake-queue').write_text('1792610000\t1\tcheck\tdisposable\tretained feedback\n')
    saved_queue=(state/'.wake-queue').read_bytes()
    for kind in ['legacy','malformed','empty','missing']:
        if kind=='legacy':identity.write_bytes(original.removeprefix(b'ps-utc-v1='))
        elif kind=='malformed':identity.write_text('unknown identity\n')
        elif kind=='empty':identity.write_bytes(b'')
        else:identity.unlink()
        saved={p.name:p.read_bytes() for p in lock.iterdir() if p.is_file()}
        for args in [[],['--restart'],['--stop'],['--take-over',str(os.getpid())],['--handling-delivered','disposable','--watcher-pid',str(watch.pid)]]:
            r=run([root/'bin/fm-watch-arm.sh',*args],expected=1)
            assert 'identity is unverifiable' in r.stderr+r.stdout
            assert watch.poll() is None and saved_queue==(state/'.wake-queue').read_bytes()
            assert saved=={p.name:p.read_bytes() for p in lock.iterdir() if p.is_file()}
        print('OBSERVED: '+kind+' owner rejected every arm mode, preserved claim and feedback, and kept actual watcher alive',file=log)
        identity.write_bytes(original)
    (state/'.wake-queue').unlink()
    os.kill(watch.pid,signal.SIGCONT)
    reaper=threading.Thread(target=watch.wait);reaper.start()
    run([root/'bin/fm-watch-arm.sh','--stop']);reaper.join(timeout=15);assert not reaper.is_alive()
    print('OBSERVED: restored verified owner is stoppable through public interface\nPASS',file=log)
finally:
    if watch and watch.poll() is None:
        if original and identity.parent.exists():identity.write_bytes(original)
        os.kill(watch.pid,signal.SIGCONT);watch.terminate()
        try:watch.wait(timeout=15)
        except subprocess.TimeoutExpired:watch.kill();watch.wait()
    if home.exists():shutil.rmtree(home)
    log.close()
