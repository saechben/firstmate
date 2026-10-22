exec((__import__('pathlib').Path('.test-phase/live_checks.py').read_text()).split('\ntry:\n    report(')[0])

def readiness(kind):
    h,e=home('ready-'+kind)
    tools=h/'tools'; tools.mkdir()
    ps=tools/'ps'
    ps.write_text('''#!/bin/bash
if [ "${1:-}" = -p ] && [ "${3:-}" = -o ] && [ "${4:-}" = lstart= ] \\
   && [ -f "$FM_HOME/state/.supervise-daemon.lock/pid" ] \\
   && [ "$(cat "$FM_HOME/state/.supervise-daemon.lock/pid")" = "$2" ]; then
  printf 'reader-parent=%s target=%s\\n' "$PPID" "$2" >> "$FM_HOME/identity-readers"
  ancestor=$PPID
  for depth in 1 2 3 4; do
    [ "$ancestor" != "$2" ] || break
    ancestor=$(/bin/ps -p "$ancestor" -o ppid= | tr -d ' ')
    [ -n "$ancestor" ] || break
  done
  if [ "$ancestor" = "$2" ]; then
    : > "$FM_HOME/identity-delayed"
    while [ ! -f "$FM_HOME/release-identity" ]; do sleep 0.05; done
    if [ "$READINESS_KIND" = unknown ]; then exit 1; fi
  fi
fi
exec /bin/ps "$@"
''')
    ps.chmod(0o700)
    socket='.test-phase/ready-'+kind+'.sock'
    e.update(PATH=str(tools)+':'+e['PATH'], TMUX=socket+',0,0', FM_TEST_SEAM='1',FM_TEST_HARNESS='claude', FM_SUPERVISOR_BACKEND='tmux',FM_SUPERVISOR_TARGET='fm-lab-readiness:0',READINESS_KIND=kind,FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',FM_WEDGE_ALARM_EXEC='discard')
    launcher=None
    try:
        run(['tmux','-f','/dev/null','-S',socket,'new-session','-d','-s','fm-lab-readiness','-c',ROOT,'sleep 120'],e)
        run(['tmux','-S',socket,'set-option','-g','default-shell','/bin/bash'],e)
        run([ROOT/'bin/fm-afk-contract.sh','enter'],e)
        output=h/'launcher-output'
        with output.open('w') as out:
            launcher=sp.Popen([ROOT/'bin/fm-afk-launch.sh','start'],env=e,stdout=out,stderr=sp.STDOUT)
            for _ in range(300):
                if (h/'identity-delayed').exists(): break
                assert launcher.poll() is None, output.read_text()
                time.sleep(.05)
            else: raise AssertionError('real daemon never reached delayed identity publication')
            pid=int((h/'state/.supervise-daemon.lock/pid').read_text())
            assert not (h/'state/.supervise-daemon.lock/pid-identity').read_text().strip()
            time.sleep(.7)
            assert launcher.poll() is None, output.read_text()
            print('Real daemon PID '+str(pid)+' is live; identity publication held for 0.7 seconds; launcher still waiting.',flush=True)
            (h/'release-identity').touch()
            rc=launcher.wait(timeout=40)
        print(output.read_text(),flush=True)
        print((h/'identity-readers').read_text(),flush=True)
        assert rc==(0 if kind=='delayed' else 2), rc
        record=(h/'state/.afk-daemon-terminal').read_text()
        print('Persisted terminal record: '+record,flush=True)
        target=record.split('\t')[1]
        run(['tmux','-S',socket,'list-sessions'],e)
        run(['tmux','-S',socket,'has-session','-t',target],e)
        os.kill(pid,0)
        if kind=='delayed':
            saved=(h/'state/.supervise-daemon.lock/pid-identity').read_text().strip()
            assert saved==identity(e,pid)
            print('Readiness succeeded with the published identity and live recorded terminal.',flush=True)
        else:
            assert (h/'state/.afk').exists() and (h/'state/.afk-contract').exists()
            assert not (h/'state/.supervise-daemon.lock/pid-identity').exists()
            print('Readiness deadline returned uncertainty while preserving daemon, posture and recorded terminal.',flush=True)
    finally:
        (h/'release-identity').touch()
        if launcher is not None and launcher.poll() is None:
            launcher.terminate(); launcher.wait(timeout=10)
        run(['tmux','-S',socket,'kill-server'],e,expected=None)
        time.sleep(.3)

try:
    report('Real daemon launch waits for delayed PID identity publication and succeeds',lambda:readiness('delayed'))
    report('A real daemon whose identity remains unreadable survives the readiness deadline with lifecycle state intact',lambda:readiness('unknown'))
finally:
    (EVIDENCE/'readiness-results.json').write_text(json.dumps(results,indent=2)+'\n')
    shutil.rmtree(BASE)
if any(r['result']=='fail' for r in results):raise SystemExit(1)
