#!/usr/bin/env bash
set -u
. "$PWD/tests/wake-helpers.sh"
TMP_ROOT=$(fm_test_tmproot cycle-reproduction)
dir=$(make_case cycle-ledger)
state="$dir/state"
cat > "$state/task.check.sh" <<'CHECK'
#!/usr/bin/env bash
printf 'done: synthetic cycle\n'
CHECK
chmod 0700 "$state/task.check.sh"
FM_STATE_OVERRIDE="$state" "$ROOT/bin/fm-check-register.sh" task
PATH="$dir/fakebin:$PATH" FM_STATE_OVERRIDE="$state" FM_GUARD_GRACE=0 FM_POLL=5 FM_SIGNAL_GRACE=1 FM_CHECK_INTERVAL=0 FM_HEARTBEAT=999999 "$ROOT/bin/fm-watch-arm.sh" > "$dir/arm.out" 2>&1
rc=$?
cat "$dir/arm.out"
printf 'arm exit=%s\n' "$rc"
for p in .watch-cycle-exits.log .watcher.err .wake-queue task.check-trust; do
  if [ -f "$state/$p" ]; then printf '%s\n' "$p"; cat "$state/$p"; fi
done
exit "$rc"
