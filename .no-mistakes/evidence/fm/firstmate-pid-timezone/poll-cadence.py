import os,pathlib,tempfile,subprocess,time,json,shutil
r=pathlib.Path.cwd(); h=pathlib.Path(tempfile.mkdtemp(prefix='cadence-',dir=r/'.test-phase'))
a=h/'board.html'; a.write_text('<h1>Disposable cadence fixture</h1>')
(h/'bin').mkdir(); b=h/'bin/lavish-axi'
b.write_text('#!/usr/bin/env python3\nimport os,time\nwith open(os.environ["CADENCE_TIMES"],"a") as f: f.write(str(time.time())+"\\n")\nprint("error: Lavish Editor poll response was interrupted\\ncode: SERVER_ERROR")\nraise SystemExit(1)\n'); b.chmod(0o755)
(h/'session').mkdir(); (h/'session/state.json').write_text(json.dumps({'sessions':{'fixture':{'file':str(a),'url':'http://127.0.0.1:14387/session/0123456789abcdef'}}}))
env={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_'))};env.update(FM_HOME=str(h),FM_STATE_OVERRIDE=str(h/'state'),LAVISH_AXI_STATE_DIR=str(h/'session'),TMPDIR=str(h),PATH=str(h/'bin')+':'+os.environ['PATH'],CADENCE_TIMES=str(h/'times'),FM_LAVISH_POLL_RETRY_DELAY='')
try:
 start=time.time(); p=subprocess.Popen(['bash',str(r/'bin/fm-procevent-lavish.sh'),'poll',str(a)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 time.sleep(6.2); p.terminate(); out,err=p.communicate(timeout=10)
 times=[float(v)-start for v in (h/'times').read_text().splitlines()] if (h/'times').exists() else []
 print(json.dumps({'invocation_seconds':times,'poll_count_after_6_2_seconds':len(times),'stdout':out,'stderr':err},indent=2))
finally:
 if p.poll() is None: p.kill();p.wait()
 shutil.rmtree(h)
