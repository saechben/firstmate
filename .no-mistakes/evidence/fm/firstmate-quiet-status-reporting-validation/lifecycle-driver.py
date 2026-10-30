import os,pathlib,subprocess,json
root=pathlib.Path.cwd(); work=root/'.test-quiet'; evidence=pathlib.Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M67568PPD081WGPMF7D84276')
transcript=[]
def call(home,args,extra=None,bad=False):
 env={k:v for k,v in os.environ.items() if not k.startswith(('FM_','TASKS_AXI_','TMUX','HERDR'))}
 env.update(FM_HOME=str(home),TMPDIR=str(work/'tmp'))
 if extra: env.update(extra)
 if bad:
  with open(home/'read-only-output','rb') as fd: p=subprocess.run(args,env=env,text=True,stdout=fd,stderr=subprocess.PIPE,timeout=45)
 else: p=subprocess.run(args,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
 transcript.append(dict(command=args,home=str(home),exit=p.returncode,stdout=p.stdout,stderr=p.stderr,stdout_read_only=bad))
 return p
for name,script in [('explicit-quiet-off',root/'bin/fm-afk-return.sh'),('publication-target',root/'bin/fm-afk-return.sh'),('publication-base',work/'baseline-bin/fm-afk-return.sh')]:
 home=work/name
 p=call(home,['bash',str(root/'bin/fm-lab-home.sh'),'create',str(home)]); assert p.returncode==0,p.stderr
 (home/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n## Done\n')
 (home/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 10\n')
 p=call(home,['bash',str(root/'bin/fm-afk-contract.sh'),'enter'],{'FM_AFK_MODE':'quiet'}); assert p.returncode==0,p.stderr
 (home/'state/.afk').write_text('quiet\n123\n')
 if name.startswith('publication'):
  (home/'read-only-output').touch()
  p=call(home,['bash',str(script),'begin'],bad=True)
 else:
  p=call(home,['bash',str(script),'begin'])
 checks={'exit':p.returncode,'flag_present':(home/'state/.afk').exists(),'record_present':(home/'state/.afk-contract').exists(),'gate_present':(home/'state/.afk-return-catchup').exists(),'archives':[x.name for x in (home/'state/afk-contracts').glob('*')]}
 transcript.append({'scenario':name,'state':checks})
 print(json.dumps({'scenario':name,'state':checks,'stderr':p.stderr,'stdout':p.stdout}),flush=True)
(evidence/'lifecycle-transcript.json').write_text(json.dumps(transcript,indent=2))
