import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

ROOT = Path.cwd()
EVIDENCE = Path('/Users/benjaminsaechew/.no-mistakes/evidence/01M5G3W75FE75Q2N34Y93N373J')
BASE = ROOT / '.test-phase' / 'manual'
BASE.mkdir(mode=0o700, exist_ok=True)
ENV = dict(os.environ)
for key in list(ENV):
    if key.startswith('FM_') or key in ('STATE', 'TMUX', 'HERDR_SESSION'):
        ENV.pop(key)
ENV.update(TMPDIR=str(ROOT / '.test-phase/tmp'), LC_ALL='C')
scenarios = []

def run(argv, env, allowed=(0,), timeout=120):
    result = subprocess.run(list(map(str, argv)), env=env, capture_output=True, text=True, timeout=timeout)
    print('$', ' '.join(map(str, argv)), flush=True)
    print('exit=', result.returncode, '\n' + result.stdout + result.stderr, flush=True)
    assert result.returncode in allowed, result
    return result

def shell(body, env, *args, allowed=(0,)):
    return run(['bash', '-c', body, '_', *args], env, allowed)

def home(name):
    path = BASE / name
    run(['bash', ROOT / 'bin/fm-lab-home.sh', 'create', path], ENV)
    return path, dict(ENV, FM_HOME=str(path), FM_STATE_OVERRIDE=str(path / 'state'),
                     FM_PROCEVENT_CLAIM_ROOT=str(path / 'claims'))

def identity(pid, env):
    return shell('. "$1/bin/fm-wake-lib.sh"; fm_pid_identity "$2"', env, ROOT, pid).stdout.strip()

def snapshot(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}

def scenario(name, function):
    print('\nSCENARIO:', name, flush=True)
    try:
        function()
        scenarios.append(dict(name=name, result='pass', live=True))
        print('OBSERVED: PASS', flush=True)
    except Exception as exc:
        scenarios.append(dict(name=name, result='fail', live=True, reason=repr(exc)))
        print('OBSERVED: FAIL', repr(exc), flush=True)

def timezone():
    path, env = home('identity')
    child = subprocess.Popen(['sleep', '120'], env=env)
    try:
        raw, stable = [], []
        for zone in ('America/Argentina/Buenos_Aires', 'Europe/Berlin'):
            zoned = dict(env, TZ=zone)
            raw.append(run(['ps', '-p', child.pid, '-o', 'lstart='], zoned).stdout.strip())
            stable.append(identity(child.pid, zoned))
        assert raw[0] != raw[1], raw
        assert stable[0] == stable[1] and stable[0].startswith('ps-utc-v1='), stable
        shell('. "$1/bin/fm-wake-lib.sh"; fm_pid_identity_compare "$2" "$3"', env, ROOT, *stable)
        shell('. "$1/bin/fm-wake-lib.sh"; fm_pid_identity_compare "$2" "$3"', env, ROOT, stable[0], stable[0] + ' changed-command', allowed=(1,))
        shell('. "$1/bin/fm-wake-lib.sh"; fm_pid_identity_compare "$2" "$3"', env, ROOT, stable[0], stable[0].removeprefix('ps-utc-v1='), allowed=(2,))
        print('Raw starts differ across timezones; tagged identities match; command mismatch=1; untagged=2.', flush=True)
    finally:
        child.terminate()
        child.wait(timeout=5)
        shutil.rmtree(path)

def process_event():
    path, env = home('listener')
    env['FM_PROCEVENT_LAUNCH_CONFIRM_SECONDS'] = '30'
    program = ROOT / 'bin/fm-procevent.sh'
    trigger = path / 'release'
    claim = path / 'claims/live-test-source.claim'
    saved = None
    legacy_written = False
    def pe(*args, zone='Europe/Berlin', allowed=(0,)):
        return run(['bash', program, *args], dict(env, TZ=zone), allowed)
    try:
        pe('register', 'lavish', 'live-test-source', '--', '/bin/bash', '-c',
           'while [ ! -f "$1" ]; do sleep 0.1; done; printf "retained review feedback\\n"', '_', trigger)
        pe('reconcile', zone='America/Argentina/Buenos_Aires')
        for _ in range(100):
            if claim.exists():
                break
            time.sleep(.1)
        assert claim.exists(), 'listener did not acquire a claim'
        saved = claim.read_bytes()
        for zone in ('America/Argentina/Buenos_Aires', 'Europe/Berlin'):
            output = pe('list', zone=zone).stdout
            assert 'live-test-source' in output and 'live ' in output, output
        duplicate = pe('start', 'live-test-source').stdout
        assert 'already owned' in duplicate, duplicate
        assert claim.read_bytes() == saved
        lines = saved.decode().splitlines()
        assert lines[3].startswith('ps-utc-v1='), lines
        lines[3] = lines[3].removeprefix('ps-utc-v1=')
        claim.write_text('\n'.join(lines) + '\n')
        legacy_written = True
        unknown = claim.read_bytes()
        assert 'uncertain' in pe('list').stdout
        reconciled = pe('reconcile').stdout
        assert 'started=0' in reconciled and 'uncertain=1' in reconciled, reconciled
        refused = pe('retire', 'live-test-source', allowed=(1,))
        assert 'cannot confirm runner identity' in refused.stderr
        assert claim.read_bytes() == unknown
        print('Legacy identity refused retirement/replacement and preserved the active claim.', flush=True)
        claim.write_bytes(saved)
        legacy_written = False
        trigger.touch()
        results = []
        for _ in range(150):
            results = list((path / 'state/procevent-inbox').glob('live-test-source.*.result'))
            if results and (path / 'state/.wake-queue').exists():
                break
            time.sleep(.1)
        assert results, 'result not persisted'
        for result in results:
            print('PERSISTED RESULT:', result.read_text(), flush=True)
        queue = (path / 'state/.wake-queue').read_text()
        print('PERSISTED WAKE:', queue, flush=True)
        assert 'retained review feedback' in results[0].read_text()
        assert 'procevent lavish live-test-source 1' in queue
        for _ in range(100):
            if not claim.exists():
                break
            time.sleep(.1)
        assert not claim.exists(), 'completed listener did not release its claim'
    finally:
        if legacy_written and saved and claim.exists():
            claim.write_bytes(saved)
        trigger.touch()
        pe('retire', 'live-test-source')
        shutil.rmtree(path)

def daemon_ownership():
    path, env = home('daemon-owner')
    env.update(FM_TEST_SEAM='1', FM_TEST_HARNESS='claude', FM_SUPERVISOR_TARGET='disposable-only', FM_SUPERVISOR_BACKEND='tmux')
    (path / 'config/supervision-host-off').touch()
    launch = ROOT / 'bin/fm-afk-launch.sh'
    child = subprocess.Popen(['sleep', '120'], env=env)
    try:
        run(['bash', launch, 'enter', '--words', 'isolated ownership proof'], env)
        owner = path / 'state/.supervise-daemon.lock'
        owner.mkdir()
        (owner / 'pid').write_text(str(child.pid))
        (owner / 'pid-identity').write_text(identity(child.pid, dict(env, TZ='America/Argentina/Buenos_Aires')) + '\n')
        stable_before = snapshot(path / 'state')
        run(['bash', launch, 'reconcile'], dict(env, TZ='Europe/Berlin'))
        assert snapshot(path / 'state') == stable_before and child.poll() is None
        print('New daemon identity recorded in Buenos Aires was recognized unchanged in Berlin.', flush=True)
        old = run(['ps', '-p', child.pid, '-o', 'lstart=', '-o', 'command='], dict(env, TZ='America/Argentina/Buenos_Aires')).stdout
        (owner / 'pid-identity').write_text(old)
        (path / 'state/.afk').write_text('away\nretained timestamp\n')
        (path / 'state/.afk-daemon-terminal').write_text('tmux\tdisposable-terminal\towned\n')
        (path / 'state/.subsuper-escalations').write_text('retained feedback\n')
        before = snapshot(path / 'state')
        for action in ('start', 'start-native', 'stop', 'reconcile'):
            output = run(['bash', launch, action], env, allowed=(2,))
            assert 'unverifiable' in output.stderr
            assert child.poll() is None and snapshot(path / 'state') == before, action
        run(['bash', ROOT / 'bin/fm-afk-start.sh'], env, allowed=(1,))
        assert snapshot(path / 'state') == before and child.poll() is None
        print('Every lifecycle operation preserved claim, terminal, posture, feedback, and live PID.', flush=True)
        owner.rename(path / 'state/.afk-launch.lock')
        before = snapshot(path / 'state')
        blocked = run(['bash', launch, 'stop'], env, allowed=(1,))
        assert 'live launcher identity is unverifiable' in blocked.stderr
        assert child.poll() is None and snapshot(path / 'state') == before
        print('Unknown live launcher lock also refused reclamation and preserved all lifecycle bytes.', flush=True)
    finally:
        child.terminate()
        child.wait(timeout=5)
        shutil.rmtree(path)

def readiness():
    path, env = home('readiness')
    owner = path / 'state/.supervise-daemon.lock'
    owner.mkdir()
    child = subprocess.Popen(['sleep', '120'], env=env)
    try:
        (owner / 'pid').write_text(str(child.pid))
        stable = identity(child.pid, env)
        for initial in ('missing', 'empty'):
            record = owner / 'pid-identity'
            record.unlink(missing_ok=True)
            if initial == 'empty':
                record.touch()
            publisher = subprocess.Popen(['bash', '-c', 'sleep 0.3; printf "%s\\n" "$2" > "$1"', '_', str(record), stable], env=env)
            try:
                run(['bash', '-c', '. "$1/bin/fm-afk-launch.sh"; fm_afk_launch_commit_terminal tmux disposable-terminal owned', '_', ROOT], env)
                publisher.wait(timeout=5)
                assert record.read_text().strip() == stable
                assert (path / 'state/.afk-daemon-terminal').exists()
                print('Readiness continued through', initial, 'identity and accepted its later publication.', flush=True)
            finally:
                if publisher.poll() is None:
                    publisher.terminate()
                    publisher.wait(timeout=5)
        record.write_text('unverifiable\n')
        before = snapshot(path / 'state')
        run(['bash', '-c', '. "$1/bin/fm-afk-launch.sh"; fm_afk_launch_commit_terminal tmux disposable-terminal owned 1', '_', ROOT], env, allowed=(2,))
        assert snapshot(path / 'state') == before and child.poll() is None
        print('Persistent readiness uncertainty returned 2 and preserved all lifecycle records.', flush=True)
    finally:
        child.terminate()
        child.wait(timeout=5)
        shutil.rmtree(path)

def watcher():
    path, env = home('watcher')
    watch = ROOT / 'bin/fm-watch.sh'
    arm = ROOT / 'bin/fm-watch-arm.sh'
    env.update(FM_POLL='0.2', FM_SIGNAL_GRACE='1', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999')
    output = open(path / 'watcher.log', 'w')
    child = subprocess.Popen(['bash', str(watch)], env=dict(env, TZ='America/Argentina/Buenos_Aires'), stdout=output, stderr=output)
    try:
        owner = path / 'state/.watch.lock'
        for _ in range(100):
            if (owner / 'pid-identity').exists() and (path / 'state/.last-watcher-beat').exists():
                break
            time.sleep(.1)
        assert (owner / 'pid-identity').read_text().startswith('ps-utc-v1=')
        assert child.poll() is None
        reaper = threading.Thread(target=child.wait)
        reaper.start()
        stopped = run(['bash', arm, '--stop'], dict(env, TZ='Europe/Berlin'))
        assert 'stopped pid=' + str(child.pid) in stopped.stdout
        reaper.join(timeout=10)
        assert not reaper.is_alive()
        print('Actual watcher started in Buenos Aires was verified and stopped in Berlin.', flush=True)
        child = subprocess.Popen(['sleep', '120'], env=env)
        owner.mkdir(exist_ok=True)
        (owner / 'pid').write_text(str(child.pid))
        (owner / 'fm-home').write_text(str(path) + '\n')
        (owner / 'watcher-path').write_text(str(watch) + '\n')
        old = run(['ps', '-p', child.pid, '-o', 'lstart=', '-o', 'command='], env).stdout
        (owner / 'pid-identity').write_text(old)
        (path / 'state/.wake-queue').write_text('1\t1\tcheck\tretained\tretained feedback\n')
        before = snapshot(path / 'state')
        for action in ('--restart', '--stop'):
            result = run(['bash', arm, action], env, allowed=(1,))
            assert 'identity is unverifiable' in result.stdout + result.stderr
            assert child.poll() is None and snapshot(path / 'state') == before
        print('Unknown live watcher owner refused restart and stop, preserving feedback and claim.', flush=True)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)
        output.close()
        shutil.rmtree(path)

def grant():
    path, env = home('grant')
    try:
        shell('. "$1/bin/fm-wake-lib.sh"; fm_wake_append check retained "check: retained feedback"', env, ROOT)
        program = ROOT / 'bin/fm-wake-grant.sh'
        run(['bash', program, 'activate', os.getpid(), 'live-test-owner'], env)
        run(['bash', program, 'publish', 'live-test-owner', '1'], env)
        owner = path / 'state/.branch-eligible-owner'
        lines = owner.read_text().splitlines()
        lines[2] = lines[2].removeprefix('ps-utc-v1=')
        owner.write_text('\n'.join(lines) + '\n')
        before = snapshot(path / 'state')
        for actor in ('main', 'branch'):
            output = run(['bash', ROOT / 'bin/fm-wake-drain.sh'], dict(env, FM_SUPERVISION_ACTOR=actor), allowed=(1,))
            assert 'owner identity is unverifiable' in output.stderr
            assert snapshot(path / 'state') == before
        print('Both drain actors refused the unknown owner and preserved queue, grant rows, and owner bytes.', flush=True)
    finally:
        shutil.rmtree(path)

scenario('New process identities remain equal after Buenos Aires to Berlin timezone change and reject changed commands', timezone)
scenario('A live listener survives timezone change, refuses legacy-owner retirement, and persists released feedback', process_event)
scenario('Daemon lifecycle operations refuse an unknown live owner without changing retained state', daemon_ownership)
scenario('Readiness waits for missing or empty identity publication and preserves persistent uncertainty', readiness)
scenario('A watcher started in Buenos Aires stops in Berlin; an unknown live owner refuses restart and stop', watcher)
scenario('Main and branch drain preserve feedback and grant rows when a live grant owner is unverifiable', grant)
(EVIDENCE / 'manual-scenarios.json').write_text(json.dumps(scenarios, indent=2) + '\n')
shutil.rmtree(BASE)
raise SystemExit(any(s['result'] != 'pass' for s in scenarios))
