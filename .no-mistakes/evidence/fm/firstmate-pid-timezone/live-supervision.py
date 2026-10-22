import os, subprocess, pathlib, time, tempfile, shutil, threading, json
R=pathlib.Path.cwd()
E=pathlib.Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J')
base={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_'))}
base['TMPDIR']=str(R/'.test-phase/tmp')
base['LC_ALL']='C'
Z=['America/Argentina/Buenos_Aires','Europe/Berlin']
results=[]
owned=[]
homes=[]
def run(argv,env,ok=None):
 p=subprocess.run(list(map(str,argv)),env=env,capture_output=True,text=True,timeout=70)
 print('$', ' '.join(map(str,argv)),flush=True)
 print('TZ='+env.get('TZ','')+' rc='+str(p.returncode)+'\n'+p.stdout+p.stderr,flush=True)
 if ok is not None: assert p.returncode==ok, p
 return p
def home(name):
 h=R/'.test-phase'/name
 run(['bash',R/'bin/fm-lab-home.sh','create',h],base,0)
 homes.append(h)
 env=dict(base,FM_HOME=str(h),FM_STATE_OVERRIDE=str(h/'state'),FM_CONFIG_OVERRIDE=str(h/'config'),FM_PROCEVENT_CLAIM_ROOT=str(h/'claims'),TZ=Z[0])
 return h,env
def shell(body,args,env,ok=None):
 return run(['bash','-c',body,'_',*args],env,ok)
def identity(pid,env):
 return shell('. "$1"; fm_pid_identity "$2"',[R/'bin/fm-wake-lib.sh',pid],env,0).stdout.strip()
def wait(check):
 for _ in range(300):
  if check(): return
  time.sleep(.1)
 raise AssertionError('observable product state did not arrive')
def scenario(name,fn):
 try: fn(); results.append(dict(name=name,result='pass',live=True)); print('SCENARIO PASS:',name,flush=True)
 except Exception as e: results.append(dict(name=name,result='fail',live=True,error=repr(e))); print('SCENARIO FAIL:',name,repr(e),flush=True)
def sleeper():
 p=subprocess.Popen(['sleep','300'],env=base); owned.append(p); return p
def snap(path):
 return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file()}
try:
 h,env=home('identity')
 def stable():
  p=sleeper(); values=[]
  for z in Z:
   en=dict(env,TZ=z,COLUMNS='20',LC_TIME='de_DE.UTF-8')
   run(['ps','-p',p.pid,'-o','lstart=','-o','command='],dict(en,LC_ALL='C'),0)
   values.append(identity(p.pid,en))
  assert values[0]==values[1] and values[0].startswith('ps-utc-v1=')
  shell('. "$1"; fm_pid_identity_compare "$2" "$3"',[R/'bin/fm-wake-lib.sh',*values],env,0)
 scenario('A newly recorded real process retains the same identity across Buenos Aires and Berlin',stable)
 def mismatches():
  p=sleeper(); original=identity(p.pid,env); time.sleep(1.1); q=sleeper()
  shell('. "$1"; fm_pid_identity_compare "$2" "$3"',[R/'bin/fm-wake-lib.sh',identity(q.pid,env),original],env,1)
  marker=h/'exec'
  q=subprocess.Popen(['bash','-c','while [ ! -f "$1" ]; do sleep .1; done; exec sleep 299','_',str(marker)],env=env); owned.append(q)
  before=identity(q.pid,env); marker.touch()
  wait(lambda: subprocess.check_output(['ps','-p',str(q.pid),'-o','command='],text=True).split()[-2:]==['sleep','299'])
  shell('. "$1"; fm_pid_identity_compare "$2" "$3"',[R/'bin/fm-wake-lib.sh',identity(q.pid,env),before],env,1)
  shell('. "$1"; fm_pid_identity_compare "$2" "$3"',[R/'bin/fm-wake-lib.sh',original,original.removeprefix('ps-utc-v1=')],env,2)
 scenario('Real start and command changes still fail identity checks; untagged identity stays unverifiable',mismatches)
 hp,ep=home('listener')
 def pe(*args,zone=Z[0],ok=None): return run([R/'bin/fm-procevent.sh',*args],dict(ep,TZ=zone),ok)
 release=hp/'release'
 def listener():
  pe('register','lavish','lab-timezone','--','/bin/sh','-c','while [ ! -f "$1" ]; do sleep .1; done; printf "retained review feedback\\n"','_',release,ok=0)
  pe('ensure-listening','lab-timezone',ok=0)
  claim=hp/'claims/lab-timezone.claim'; wait(claim.exists)
  old=claim.read_bytes()
  for z in Z:
   p=pe('list',zone=z,ok=0); assert 'live' in p.stdout
   p=pe('reconcile',zone=z,ok=0); assert 'started=0' in p.stdout
   assert claim.read_bytes()==old
  release.touch()
  inbox=hp/'state/procevent-inbox'
  wait(lambda:any(inbox.glob('lab-timezone.*.result')))
  out=next(inbox.glob('lab-timezone.*.result')); assert out.read_text()=='retained review feedback\n'
  print('DURABLE RESULT:',out.read_text(),flush=True)
  wait((hp/'state/.wake-queue').exists)
  print('DURABLE WAKE QUEUE:',(hp/'state/.wake-queue').read_text(),flush=True)
 scenario('A real blocking listener survives timezone changes without replacement and durably captures feedback',listener)
 def unknown_listener():
  pe('retire','lab-timezone',ok=0)
  p=sleeper()
  (hp/'state/lab-task.meta').write_text('backend=tmux\nwindow=lab-session:fm-lab-task\nproject=lab\nworktree='+str(hp/'retained-work')+'\n')
  pe('register-task','lavish','lab-uncertain','lab-task','--','/bin/true',ok=0)
  (hp/'retained-work').mkdir(); (hp/'retained-work/review.txt').write_text('retained work\n')
  shell('. "$1/bin/fm-wake-lib.sh"; . "$1/bin/fm-pr-lib.sh"; . "$1/bin/fm-procevent-lib.sh"; fm_procevent_source_lock_acquire "$2" || exit; fm_procevent_claim_acquire_locked "$2" "$FM_HOME" "$3" "$STATE/procevent/$2.source" "$STATE"; rc=$?; fm_procevent_source_lock_release "$2"; exit "$rc"',[R,'lab-uncertain',p.pid],ep,0)
  claim=hp/'claims/lab-uncertain.claim'; lines=claim.read_text().splitlines(); lines[3]=lines[3].removeprefix('ps-utc-v1='); claim.write_text('\n'.join(lines)+'\n')
  saved=claim.read_bytes(); retained=snap(hp/'state/procevent-inbox')
  assert '/uncertain' in pe('list',zone=Z[1],ok=0).stdout
  out=pe('reconcile',zone=Z[1],ok=0); assert 'uncertain=1' in out.stdout and 'started=0' in out.stdout
  out=pe('retire','lab-uncertain',zone=Z[1]); assert out.returncode!=0 and 'cannot confirm runner identity' in out.stderr
  assert p.poll() is None and claim.read_bytes()==saved and retained==snap(hp/'state/procevent-inbox')
  assert (hp/'retained-work/review.txt').read_text()=='retained work\n'
  print('CLAIM AND RETAINED RESULT BYTES UNCHANGED; OWNED PROCESS ALIVE',flush=True)
  p.terminate(); p.wait(); pe('retire','lab-uncertain',ok=0)
 scenario('Unknown live legacy listener refuses replacement and retirement while preserving feedback and work',unknown_listener)
 hw,ew=home('watcher')
 def watcher():
  p=sleeper(); lock=hw/'state/.watch.lock'; lock.mkdir()
  for key,val in {'pid':str(p.pid),'fm-home':str(hw),'watcher-path':str(R/'bin/fm-watch.sh'),'pid-identity':subprocess.check_output(['ps','-p',str(p.pid),'-o','lstart=','-o','command='],env=ew,text=True)}.items(): (lock/key).write_text(val+'\n')
  (hw/'state/.wake-queue').write_text('1\t1\tcheck\tlab\tretained feedback\n')
  before=snap(hw/'state')
  for args in [[],['--restart'],['--stop'],['--take-over',str(os.getpid())],['--handling-delivered','lab-generation','--watcher-pid',str(p.pid)]]:
   out=run([R/'bin/fm-watch-arm.sh',*args],dict(ew,TZ=Z[1])); assert out.returncode!=0 and 'identity is unverifiable' in out.stderr
   assert p.poll() is None and snap(hw/'state')==before
  print('ALL WATCHER MODES PRESERVED CLAIM AND FEEDBACK WITHOUT SIGNAL OR REPLACEMENT',flush=True)
 scenario('Every watcher arm, restart, stop and takeover mode preserves an unverifiable live owner',watcher)
 hd,ed=home('daemon')
 def daemon():
  run([R/'bin/fm-afk-contract.sh','enter','--words','disposable ownership check'],dict(ed,FM_AFK_MODE='quiet'),0)
  p=sleeper(); lock=hd/'state/.supervise-daemon.lock'; lock.mkdir(); (lock/'pid').write_text(str(p.pid))
  (lock/'pid-identity').write_text(identity(p.pid,ed).removeprefix('ps-utc-v1=')+'\n')
  (hd/'state/.afk').write_text('quiet\nretained timestamp\n')
  (hd/'state/.afk-daemon-terminal').write_text('tmux\tdisposable-terminal\towned\n')
  (hd/'state/.wake-queue').write_text('retained feedback\n')
  before={k:v for k,v in snap(hd/'state').items() if not k.startswith('.afk-launch.lock')}
  for command in [[R/'bin/fm-afk-start.sh'],*[ [R/'bin/fm-afk-launch.sh',mode] for mode in ['start','start-native','stop','reconcile']]]:
   out=run(command,dict(ed,TZ=Z[1],FM_SUPERVISOR_TARGET='disposable-primary',FM_SUPERVISOR_BACKEND='tmux')); assert out.returncode!=0 and 'identity is unverifiable' in out.stderr
   assert p.poll() is None and snap(hd/'state')==before
  print('DAEMON CLAIM, POSTURE, TERMINAL AND FEEDBACK UNCHANGED',flush=True)
 scenario('Daemon lifecycle commands refuse uncertain ownership without signalling or changing retained state',daemon)
 def ready():
  for kind in ['missing','empty','persistent-unknown']:
   hr,er=home('ready-'+kind); lock=hr/'state/.supervise-daemon.lock'; lock.mkdir(); p=sleeper(); (lock/'pid').write_text(str(p.pid)); ident=identity(p.pid,er)
   if kind=='empty': (lock/'pid-identity').write_text('')
   if kind=='persistent-unknown': (lock/'pid-identity').write_text(ident.removeprefix('ps-utc-v1=')+'\n')
   else:
    def publish(path=lock/'pid-identity',value=ident): time.sleep(.5); path.write_text(value+'\n')
    t=threading.Thread(target=publish); t.start()
   start=time.monotonic()
   # Existing executable readiness/commit interface; the real poll and identity checks run unmodified.
   out=shell('. "$1"; fm_afk_launch_commit_terminal tmux disposable-terminal owned',[R/'bin/fm-afk-launch.sh'],er)
   elapsed=time.monotonic()-start
   if kind!='persistent-unknown':
    t.join(); assert out.returncode==0 and (hr/'state/.afk-daemon-terminal').exists()
   else:
    assert out.returncode==2 and elapsed>=5 and (hr/'state/.afk-daemon-terminal').exists()
   assert p.poll() is None
   print('READINESS',kind,'elapsed_seconds',round(elapsed,2),'terminal_record', (hr/'state/.afk-daemon-terminal').read_text(),flush=True)
 scenario('Readiness tolerates delayed identity publication and preserves the terminal after persistent uncertainty',ready)
 hg,eg=home('grant')
 def grant():
  p=sleeper(); state=hg/'state'; (state/'.wake-queue').write_text('1\t1\tsignal\tlab-task.status\tsignal: retained feedback\n')
  run([R/'bin/fm-wake-grant.sh','activate',p.pid,'lab-generation'],eg,0)
  run([R/'bin/fm-wake-grant.sh','publish','lab-generation','1'],eg,0)
  owner=state/'.branch-eligible-owner'; lines=owner.read_text().splitlines(); lines[2]=lines[2].removeprefix('ps-utc-v1='); owner.write_text('\n'.join(lines)+'\n')
  tracked=['.wake-queue','.branch-eligible-owner','.branch-eligible-rows']; before={k:(state/k).read_bytes() for k in tracked}
  for actor in ['main','branch']:
   out=run([R/'bin/fm-wake-drain.sh'],dict(eg,FM_SUPERVISION_ACTOR=actor)); assert out.returncode!=0 and 'owner identity is unverifiable' in out.stderr
   assert all((state/k).read_bytes()==v for k,v in before.items())
  print('BOTH ACTORS PRESERVED GRANT, OWNER AND QUEUE BYTES',flush=True)
 scenario('Neither actor drains feedback or reclaims a grant with an unverifiable live owner',grant)
finally:
 for p in owned:
  if p.poll() is None: p.terminate()
  try: p.wait(timeout=5)
  except subprocess.TimeoutExpired: p.kill(); p.wait()
 for h in homes:
  if h==locals().get('hp'):
   for source in ['lab-timezone','lab-uncertain']:
    try: pe('retire',source)
    except Exception as e: print('CLEANUP ERROR',repr(e),flush=True)
  shutil.rmtree(h)
 (E/'live-scenarios.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2),flush=True)
assert all(x['result']=='pass' for x in results)
