import os, pathlib, subprocess, time, signal, shutil, json
r=pathlib.Path.cwd(); e=pathlib.Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J')
sock='.test-phase/readiness.sock'
base={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_'))}
base['TMPDIR']=str(r/'.test-phase/tmp')
def cmd(a,env=base):
 p=subprocess.run(list(map(str,a)),env=env,capture_output=True,text=True,timeout=30)
 print('$',' '.join(map(str,a)),'rc=',p.returncode,'\n'+p.stdout+p.stderr,flush=True)
 return p
server=cmd(['tmux','-S',sock,'display-message','-p','-t','lab-receiver','#{socket_path},#{pid},0']).stdout.strip()
results=[]
try:
 for kind in ['transient-missing','persistent-missing']:
  h=r/'.test-phase'/('real-daemon-'+kind); pid=None; launch=None; saved=None
  cmd(['bash',r/'bin/fm-lab-home.sh','create',h])
  env=dict(base,FM_HOME=str(h),FM_SUPERVISOR_TARGET='lab-receiver:0',FM_SUPERVISOR_BACKEND='tmux',TMUX=server,TZ='Europe/Berlin')
  (h/'config/supervision-host-off').touch()
  cmd(['bash',r/'bin/fm-afk-contract.sh','enter','--words','disposable real-daemon readiness check'],env)
  identity=h/'state/.supervise-daemon.lock/pid-identity'
  try:
   launch=subprocess.Popen(['bash',str(r/'bin/fm-afk-launch.sh'),'start'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   pidfile=h/'state/.supervise-daemon.lock/pid'
   end=time.monotonic()+15
   while time.monotonic()<end:
    if pidfile.exists():
     try: pid=int(pidfile.read_text().strip())
     except (ValueError,FileNotFoundError): continue
     if pid>1:
      os.kill(pid,signal.SIGSTOP)
      break
    if launch.poll() is not None: break
    time.sleep(.0005)
   assert pid and launch.poll() is None, 'launch completed before the readiness cut could be driven'
   # All affected state and the paused process belong to this newly minted lab.
   saved=cmd(['bash','-c','. "$1"; fm_pid_identity "$2"','_',r/'bin/fm-wake-lib.sh',pid],env).stdout.strip()
   assert saved.startswith('ps-utc-v1=')
   if identity.exists(): identity.unlink()
   time.sleep(.35)
   assert launch.poll() is None, 'public launch returned during transient missing identity'
   print('OBSERVED: public start remains pending while its actual daemon has no readable identity',flush=True)
   if kind=='transient-missing':
    identity.write_text(saved+'\n'); os.kill(pid,signal.SIGCONT)
   out,err=launch.communicate(timeout=30)
   print('PUBLIC START RESULT:',launch.returncode,'\n'+out+err,flush=True)
   rec=h/'state/.afk-daemon-terminal'
   assert rec.exists() and (h/'state/.afk').exists()
   if kind=='transient-missing':
    assert launch.returncode==0 and 'daemon launched in detached tmux session' in err
   else:
    assert launch.returncode==2 and 'preserving daemon terminal' in err
    identity.write_text(saved+'\n'); os.kill(pid,signal.SIGCONT)
   print('RETAINED TERMINAL:',rec.read_text(),flush=True)
   results.append({'name':kind,'result':'pass','live':True})
  except Exception as ex:
   results.append({'name':kind,'result':'fail','live':True,'error':repr(ex)})
   print('FAIL:',repr(ex),flush=True)
  finally:
   if pid:
    try:
     if saved and identity.parent.exists(): identity.write_text(saved+'\n')
     os.kill(pid,signal.SIGCONT)
    except ProcessLookupError: pass
   if launch and launch.poll() is None:
    try: launch.communicate(timeout=15)
    except subprocess.TimeoutExpired: launch.terminate();launch.communicate(timeout=15)
   cmd(['bash',r/'bin/fm-afk-launch.sh','stop'],env)
   if pid:
    try: os.kill(pid,signal.SIGTERM)
    except ProcessLookupError: pass
   shutil.rmtree(h)
finally:
 cmd(['tmux','-S',sock,'kill-server'])
 (e/'daemon-readiness-live.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2),flush=True)
assert len(results)==2 and all(x['result']=='pass' for x in results)
