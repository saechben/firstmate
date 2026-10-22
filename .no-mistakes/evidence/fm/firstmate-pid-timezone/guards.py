exec((__import__('pathlib').Path('.test-phase/live_checks.py').read_text()).split('\ntry:\n    report(')[0])

def claim(e,h,pid,source):
    task=source+'-task'
    (h/('state/'+task+'.meta')).write_text('backend=tmux\nwindow=fm-lab:fm-'+task+'\nworktree='+str(h/'retained-work')+'\nproject=fm-lab\n')
    pe(e,'register-task','lavish',source,task,'--','/bin/true')
    shell(e,'. "$1/bin/fm-wake-lib.sh"; . "$1/bin/fm-pr-lib.sh"; . "$1/bin/fm-procevent-lib.sh"; fm_procevent_source_lock_acquire "$3" || exit; fm_procevent_claim_acquire_locked "$3" "$FM_HOME" "$2" "$STATE/procevent/$3.source" "$STATE"; rc=$?; fm_procevent_source_lock_release "$3"; exit "$rc"',ROOT,pid,source)
    return h/('claims/'+source+'.claim')

def strict_guards():
    h,e=home('guards')
    trigger=h/'exec'
    p=sp.Popen(['bash','-c','while [ ! -f "$1" ]; do sleep 0.05; done; exec sleep 119','_',str(trigger)],env=e)
    owned.append(p)
    time.sleep(.15)
    path=claim(e,h,p.pid,'command-guard')
    original=path.read_text().splitlines()[3]
    start=run(['/bin/ps','-p',p.pid,'-o','lstart='],e).stdout
    print('Original recorded command: '+original,flush=True)
    trigger.touch()
    for _ in range(100):
        if 'sleep 119' in run(['/bin/ps','-p',p.pid,'-o','command='],e,show=False).stdout:break
        time.sleep(.05)
    else:raise AssertionError('exec never changed command')
    assert run(['/bin/ps','-p',p.pid,'-o','lstart='],e).stdout==start
    assert '/dead' in pe(e,'list').stdout
    pe(e,'retire','command-guard')
    assert p.poll() is None
    first=sleep_child(e)
    prior=identity(e,first.pid)
    time.sleep(1.2)
    later=sleep_child(e)
    path=claim(e,h,later.pid,'start-guard')
    current=identity(e,later.pid)
    print('Prior identity: '+prior+'\nLater identity: '+current,flush=True)
    assert prior!=current
    assert run(['/bin/ps','-p',first.pid,'-o','command='],e).stdout==run(['/bin/ps','-p',later.pid,'-o','command='],e).stdout
    lines=path.read_text().splitlines();lines[3]=prior
    path.write_text('\n'.join(lines)+'\n')
    assert '/dead' in pe(e,'list').stdout
    pe(e,'retire','start-guard')
    assert first.poll() is None and later.poll() is None
    print('Changed command and changed start both refused ownership; retire signalled neither live process.',flush=True)

def proc_contract():
    h,e=home('proc')
    p=sleep_child(e)
    proc=h/'proc'; proc.mkdir()
    process=proc/str(p.pid);process.mkdir()
    def write(start):
        (process/'stat').write_text(f'{p.pid} (name ) with spaces) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 {start} 20 21 22\n')
        (process/'cmdline').write_bytes(b'sleep\x00120\x00')
    write(987654)
    (proc/'stat').write_text('btime 1784094040\n')
    e['FM_PROC_ROOT_OVERRIDE']=str(proc)
    path=claim(e,h,p.pid,'proc-guard')
    original=path.read_bytes()
    print('Stored compatible /proc identity: '+path.read_text().splitlines()[3],flush=True)
    assert '/listening' in pe(e,'list').stdout
    (proc/'stat').write_text('btime 1784094016\n')
    assert '/listening' in pe(e,'list').stdout and path.read_bytes()==original
    write(987655)
    assert '/dead' in pe(e,'list').stdout
    pe(e,'retire','proc-guard')
    assert p.poll() is None
    print('Disposable /proc data: wall-clock btime changed without ownership loss; changed starttime rejected and innocent process retained.',flush=True)

try:
    report('Real command changes and distinct starts reject stale ownership without signalling unrelated live processes',strict_guards)
    report('Compatible proc records ignore wall-clock changes and detect reused starttime',proc_contract)
finally:
    for p in owned:
        if p.poll() is None:p.terminate()
        p.wait(timeout=10)
    shutil.rmtree(BASE)
    (EVIDENCE/'guard-results.json').write_text(json.dumps(results,indent=2)+'\n')
if any(r['result']=='fail' for r in results):raise SystemExit(1)
