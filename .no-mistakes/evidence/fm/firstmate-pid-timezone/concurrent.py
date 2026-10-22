exec((__import__('pathlib').Path('.test-phase/live_checks.py').read_text()).split('\ntry:\n    report(')[0])

def concurrent():
    for attempt in range(1,2):
        h,e=home('concurrent-'+str(attempt))
        print('Concurrent drain attempt '+str(attempt),flush=True)
        e['FM_ROOT_OVERRIDE']=str(h)
        processes=[]
        errors=(EVIDENCE/f'concurrent-writers-{attempt}.log').open('w')
        for i in range(1,41):
            p=sp.Popen(['bash','-c','. "$1"; fm_wake_append signal "$2" "signal: retained feedback $2"','_',str(ROOT/'bin/fm-wake-lib.sh'),'row-'+str(i)],env=e,stdout=sp.DEVNULL,stderr=errors,text=True)
            processes.append(p)
        trace=(EVIDENCE/f'concurrent-drain-{attempt}.trace').open('w')
        drain=sp.Popen(['bash','-x',str(ROOT/'bin/fm-wake-drain.sh')],env=e,stdout=sp.PIPE,stderr=trace,text=True)
        try:
            failures=[]
            deadline=time.monotonic()+120
            while any(p.poll() is None for p in processes) and time.monotonic()<deadline:
                time.sleep(.1)
            for p in processes:
                if p.poll() is None:failures.append((p.pid,'still active at 120-second diagnostic bound',''))
                elif p.returncode:failures.append((p.pid,p.returncode,''))
            try:
                out,_=drain.communicate(timeout=15)
                print('Drain exit='+str(drain.returncode)+'\n'+out,flush=True)
            except sp.TimeoutExpired:
                print('Drain has not returned within the bounded experiment.',flush=True)
                failures.append((drain.pid,'timeout',''))
            trace.flush()
            queue=h/'state/.wake-queue'
            rows=queue.read_text().splitlines() if queue.exists() else []
            print('Durable queue rows='+str(len(rows))+'; writer failures='+str(failures),flush=True)
            locks=[]
            for f in (h/'state').iterdir():
                if '.lock' not in f.name:continue
                if f.is_symlink():locks.append((f.name,'symlink',os.readlink(f)))
                elif f.is_dir():locks.append((f.name,{x.name:x.read_text(errors='replace') for x in f.iterdir() if x.is_file()}))
            print('Remaining lock state: '+json.dumps(locks),flush=True)
            assert not failures and drain.returncode==0 and len(rows)==40
        finally:
            for p in [drain,*processes]:
                if p.poll() is None:p.terminate()
            for p in [drain,*processes]:
                try:p.wait(timeout=5)
                except sp.TimeoutExpired:p.kill();p.wait()
            trace.close()
            errors.close()

try:
    report('Concurrent append and drain preserves every queued feedback record',concurrent)
finally:
    shutil.rmtree(BASE)
    (EVIDENCE/'concurrent-results.json').write_text(json.dumps(results,indent=2)+'\n')
if any(r['result']=='fail' for r in results):raise SystemExit(1)
