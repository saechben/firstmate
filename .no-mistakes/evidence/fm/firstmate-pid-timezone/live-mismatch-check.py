import os, subprocess, time, shutil
from pathlib import Path
root=Path.cwd();evidence=Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J');owned=[];homes=[]
log=(evidence/'live-mismatch-transcript.log').open('w',buffering=1)
base={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['HERDR_SESSION','HERDR_ENV','PI_CODING_AGENT','FM_PI_HARNESS']}
base.update(TMPDIR=str(root/'.test-phase-tmp/tmp'),FM_TEST_HARNESS='claude',FM_TEST_SEAM='1',CLAUDECODE='1',LC_ALL='C',TZ='Europe/Berlin',TMUX='.test-phase-tmp/lab.sock,0,0')
def run(argv,env):
    r=subprocess.run(list(map(str,argv)),env=env,capture_output=True,text=True,timeout=35)
    print('$ '+' '.join(map(str,argv)),r.stdout+r.stderr,'exit='+str(r.returncode),sep='\n',file=log,flush=True)
    assert r.returncode==0,r
    return r.stdout.strip()
def identity(pid,env):return run(['bash','-c','. "$1"; fm_pid_identity "$2"','_',root/'bin/fm-wake-lib.sh',pid],env)
def new_home(kind):
    home=root/('.test-phase-tmp/mismatch-'+kind);homes.append(home);env=dict(base,FM_HOME=str(home))
    run([root/'bin/fm-lab-home.sh','create',home],env);(home/'config/supervision-host-off').touch()
    run([root/'bin/fm-afk-launch.sh','enter','--words','disposable strict identity guard'],env)
    run([root/'bin/fm-afk-launch.sh','start-native'],env)
    return home,env
try:
    home,env=new_home('start')
    first=subprocess.Popen(['/bin/sleep','300'],env=env);owned.append(first);old=identity(first.pid,env);time.sleep(1.2)
    second=subprocess.Popen(['/bin/sleep','300'],env=env);owned.append(second);new=identity(second.pid,env)
    assert old!=new and old.split()[-2:]==new.split()[-2:]
    lock=home/'state/.supervise-daemon.lock';lock.mkdir();(lock/'pid').write_text(str(second.pid));(lock/'pid-identity').write_text(old+'\n')
    run([root/'bin/fm-afk-launch.sh','stop'],env)
    assert second.poll() is None and not (home/'state/.afk').exists()
    print('OBSERVED: same command with a later actual start is rejected as owner; unrelated process is not signalled',file=log)
    home,env=new_home('command')
    changing=subprocess.Popen(['/bin/bash','-c','read -r ignored; exec /bin/sleep 301'],env=env,stdin=subprocess.PIPE);owned.append(changing)
    time.sleep(.1);old=identity(changing.pid,env)
    oldstart=run(['ps','-p',str(changing.pid),'-o','lstart='],env)
    changing.stdin.write(b'continue\n');changing.stdin.flush()
    for _ in range(100):
        command=run(['ps','-p',str(changing.pid),'-o','command='],env)
        if 'sleep 301' in command:break
        time.sleep(.05)
    else:raise AssertionError('process did not exec')
    new=identity(changing.pid,env);newstart=run(['ps','-p',str(changing.pid),'-o','lstart='],env)
    assert old!=new and oldstart==newstart
    lock=home/'state/.supervise-daemon.lock';lock.mkdir();(lock/'pid').write_text(str(changing.pid));(lock/'pid-identity').write_text(old+'\n')
    run([root/'bin/fm-afk-launch.sh','stop'],env)
    assert changing.poll() is None and not (home/'state/.afk').exists()
    print('OBSERVED: actual exec on the same PID and start time invalidates ownership; changed command is not signalled\nPASS',file=log)
finally:
    for p in owned:
        if p.poll() is None:p.terminate()
        p.wait(timeout=12)
    for h in homes:
        if h.exists():shutil.rmtree(h)
    log.close()
