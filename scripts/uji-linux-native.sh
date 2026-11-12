#!/usr/bin/env bash
# One-click native Linux run of every experiment in the paper (research: isolasi multi-kasus).
#
#   git clone https://github.com/hermanka/KodeLab.git && cd KodeLab && git checkout perbaikan-audit
#   bash scripts/uji-linux-native.sh            # full run, ~40-60 min
#   bash scripts/uji-linux-native.sh --quick    # smoke run, ~10 min (fewer repeats; not for the paper)
#
# Options: --quick, --reps N (performance repeats, default 10), --force (run although other containers are
# running or the machine is on battery), --skip-perf (security tests only).
# Output: hasil-uji-linux/<host>-<time>/ and the same folder as .tar.gz. Send the .tar.gz back.
# Needs: Docker Engine + Compose v2 usable without sudo (or run the whole script with sudo), git, internet
# for the image builds. Nothing outside this repo's containers and images is changed.
set -uo pipefail

REPS=10 BASELINE=60 MATRIX_REPEATS=5 MUTATION_REPEATS=3 STARTS=20 FORCE=0 SKIP_PERF=0
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) REPS=2 BASELINE=10 MATRIX_REPEATS=1 MUTATION_REPEATS=1 STARTS=5 ;;
    --reps) REPS="$2"; shift ;;
    --force) FORCE=1 ;;
    --skip-perf) SKIP_PERF=1 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
  shift
done

cd "$(dirname "$0")/.."
REPO=$(pwd -W 2>/dev/null || pwd)  # pwd -W: host path for Docker when smoke-tested from Git Bash on Windows
S0_COMMIT=d1601c3
STAMP=$(date +%Y%m%d-%H%M%S)
NAME="$(hostname -s 2>/dev/null || hostname)-$STAMP"
OUT="hasil-uji-linux/$NAME"
OUT_HOST="$REPO/$OUT"
mkdir -p "$OUT/logs"
exec > >(tee -a "$OUT/console.log") 2>&1
export MSYS_NO_PATHCONV=1

say() { printf '\n=== %s  %s\n' "$(date +%H:%M:%S)" "$*"; }
status() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$OUT/status.tsv"; echo "--> $1: $2 ($3)"; }
# step NAME COMMAND...: runs, logs to logs/NAME.log, records ok/FAILED; never stops the script.
step() {
  local name=$1; shift
  local start=$(date +%s)
  say "$name"
  if "$@" > >(tee "$OUT/logs/$name.log") 2>&1; then
    status "$name" ok "$(( $(date +%s) - start )) s"
  else
    status "$name" "FAILED exit=$?" "$(( $(date +%s) - start )) s"
  fi
}
printf 'step\tstatus\tduration\n' > "$OUT/status.tsv"

# ---------------------------------------------------------------- 0. preflight
say "preflight"
command -v docker >/dev/null || { echo "Docker not found. Install Docker Engine (docs.docker.com/engine/install/ubuntu)."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 not found (package docker-compose-plugin)."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Cannot talk to Docker. Add yourself to the docker group (sudo usermod -aG docker \$USER, then log in again) or run with sudo."; exit 1; }
git cat-file -e "$S0_COMMIT^{commit}" 2>/dev/null || git fetch --unshallow 2>/dev/null || git fetch origin
git cat-file -e "$S0_COMMIT^{commit}" || { echo "Commit $S0_COMMIT (baseline S0) missing: check out branch perbaikan-audit."; exit 1; }

others=$(docker ps --format '{{.Names}}')
if [ -n "$others" ]; then
  echo "Running containers (they distort the CPU measurements): $others"
  [ "$FORCE" = 1 ] || { echo "Stop them first (docker stop \$(docker ps -q)) or pass --force."; exit 1; }
fi
on_battery=0
for supply in /sys/class/power_supply/*; do
  [ "$(cat "$supply/type" 2>/dev/null)" = Mains ] && [ "$(cat "$supply/online" 2>/dev/null)" = 0 ] && on_battery=1
done
if [ "$on_battery" = 1 ]; then
  echo "Running on battery: CPU throttling gives false TLE and slower timings. Plug in the charger."
  [ "$FORCE" = 1 ] || exit 1
fi

if [ ! -f .env ]; then
  rnd() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
  sed -e "s/^BOOTSTRAP_ADMIN_PASSWORD=.*/BOOTSTRAP_ADMIN_PASSWORD=$(rnd)/" -e "s/^RUNNER_TOKEN=.*/RUNNER_TOKEN=$(rnd)/" \
      -e "s/^CLASS_INVITE_SECRET=.*/CLASS_INVITE_SECRET=$(rnd)/" -e "s/^MARIADB_PASSWORD=.*/MARIADB_PASSWORD=$(rnd)/" \
      -e "s/^MARIADB_ROOT_PASSWORD=.*/MARIADB_ROOT_PASSWORD=$(rnd)/" .env.example > .env
  echo "Created .env with random secrets (it stays local, it is gitignored)."
fi

# Experiment overlay: S1 runner without warm pool next to an S0 runner with the code of commit d1601c3.
S0_DIR="$OUT/s0"
mkdir -p "$S0_DIR/code"
git archive "$S0_COMMIT" runner app | tar -x -C "$S0_DIR/code"
git archive "$S0_COMMIT" sandbox | tar -x -C "$S0_DIR"
cat > "$OUT/compose.experiment.yaml" <<EOF
services:
  runner:
    environment:
      RUNNER_WARM: '0'
      RUNNER_SLOTS: '8'
  runner-s0:
    image: judgementsystem-app:dev
    init: true
    user: '0:0'
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    networks: [platform]
    environment:
      RUNNER_TOKEN: \${RUNNER_TOKEN}
      SANDBOX_IMAGE: judgementsystem-sandbox:gcc12-v3
      RUNNER_SLOTS: '8'
    command: [uvicorn, runner.main:app, --host, 0.0.0.0, --port, '8001', --workers, '1']
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - $OUT_HOST/s0/code/runner:/app/runner:ro
      - $OUT_HOST/s0/code/app:/app/app:ro
EOF
DC=(docker compose -f compose.yaml -f "$OUT/compose.experiment.yaml")

RUNNER_WAS_UP=$(docker compose ps -q runner 2>/dev/null)
cleanup() {
  say "cleanup"
  "${DC[@]}" rm -sf runner runner-s0 >/dev/null 2>&1
  docker ps -aq --filter label=judgementsystem.sandbox=1 | xargs -r docker rm -f >/dev/null 2>&1
  [ -z "$RUNNER_WAS_UP" ] || docker compose up -d --no-deps runner  # Put back the normal runner of a running stack.
}
trap cleanup EXIT

# ---------------------------------------------------------------- 1. environment
environment() {
  echo "## date";        date -Is
  echo "## repo";        git rev-parse HEAD; git status --short
  echo "## os";          cat /etc/os-release 2>/dev/null
  echo "## uname";       uname -a
  echo "## cpu";         lscpu 2>/dev/null || cat /proc/cpuinfo | head -30
  echo "## nproc";       nproc
  echo "## memory";      free -m 2>/dev/null
  echo "## loadavg";     cat /proc/loadavg
  echo "## virt";        systemd-detect-virt 2>/dev/null || echo unknown
  echo "## cgroup";      stat -fc %T /sys/fs/cgroup
  echo "## yama ptrace_scope"; cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo absent
  echo "## lsm";         cat /sys/kernel/security/lsm 2>/dev/null || echo unreadable
  echo "## apparmor";    cat /sys/module/apparmor/parameters/enabled 2>/dev/null || echo absent
  echo "## governor";    cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort | uniq -c
  echo "## no_turbo";    cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a
  echo "## power";       for s in /sys/class/power_supply/*; do echo "$s $(cat "$s/type" 2>/dev/null) online=$(cat "$s/online" 2>/dev/null) status=$(cat "$s/status" 2>/dev/null)"; done
  echo "## docker version"; docker version
  echo "## docker info";    docker info
  echo "## compose";        docker compose version
}
step environment environment
docker info --format '{{json .}}' > "$OUT/docker-info.json" 2>/dev/null

# ---------------------------------------------------------------- 2. images
build_images() {
  docker compose build runner &&
  docker compose --profile tools build sandbox-image &&
  docker build -t judgementsystem-sandbox:gcc12-v3 "$S0_DIR/sandbox"
}
step build-images build_images
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep judgementsystem > "$OUT/images.txt"

# ---------------------------------------------------------------- 3. security tests (Lampiran A 1-22, 24-26)
step security-tests "${DC[@]}" run --rm --no-deps -T -e RUN_SANDBOX_TESTS=1 -e RUNNER_WARM=0 -v "$OUT_HOST:/results" runner \
  python -m pytest -p no:cacheprovider -v -s -rA tests/test_sandbox_reuse.py tests/test_runner_wait.py tests/test_runner_capacity.py \
  --junitxml=/results/security-tests.xml

# ---------------------------------------------------------------- 4. supervisor access matrix (Lampiran A 23, Tabel 2)
matrix() {
  local i rc=0
  for i in $(seq 1 "$MATRIX_REPEATS"); do
    echo "## repeat $i"
    "${DC[@]}" run --rm --no-deps -T runner python scripts/profiling/supervisor_access_matrix.py || rc=1
  done
  return $rc
}
step supervisor-matrix matrix

# ---------------------------------------------------------------- 5. mutation analysis (bagian 4.1)
step channel-mutation "${DC[@]}" run --rm --no-deps -T -e RUNNER_WARM=0 -e PYTHONPATH=/app -v "$OUT_HOST:/results" runner \
  python scripts/profiling/channel_mutation.py "$MUTATION_REPEATS" /results/channel-mutation.json

# ---------------------------------------------------------------- 6. raw docker start cost
docker_starts() {
  local image i t0 t1
  echo "image,i,seconds" > "$OUT/docker-start.csv"
  for image in judgementsystem-sandbox:gcc12-v4 judgementsystem-sandbox:gcc12-v3; do
    docker run --rm --network none --entrypoint /bin/true "$image" || return 1  # warm-up, not recorded
    for i in $(seq 1 "$STARTS"); do
      t0=$(date +%s%N)
      docker run --rm --network none --entrypoint /bin/true "$image" || return 1
      t1=$(date +%s%N)
      echo "$image,$i,$(awk "BEGIN{printf \"%.4f\", ($t1-$t0)/1e9}")" | tee -a "$OUT/docker-start.csv"
    done
  done
}
step docker-start docker_starts

# ---------------------------------------------------------------- 7. performance S0 vs S1 (Tabel 5-7, Gambar 3-4)
performance() {
  mkdir -p "$OUT/performance" && chmod 777 "$OUT/performance"
  "${DC[@]}" up -d --no-deps --wait runner runner-s0 || return 1
  sleep 10  # Let start-up work settle before the idle baseline.
  "${DC[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$OUT_HOST/performance:/results" api \
    python scripts/profiling/isolation_experiment.py --reps "$REPS" --baseline-seconds "$BASELINE" --out /results || return 1
  "${DC[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$OUT_HOST/performance:/results" api \
    python scripts/profiling/analyze_isolation.py /results
}
if [ "$SKIP_PERF" = 1 ]; then status performance skipped -; else step performance performance; fi
cleanup
trap - EXIT

# ---------------------------------------------------------------- 8. package
say "package"
# Files written by containers running as root: hand them back to this user so the folder can be deleted.
docker run --rm --user 0:0 --entrypoint chown -v "$OUT_HOST:/r" judgementsystem-app:dev -R "$(id -u):$(id -g)" /r 2>/dev/null
rm -rf "$S0_DIR/code"  # Copy of the repo at d1601c3, not data.
cat > "$OUT/README.txt" <<EOF
Native Linux run of scripts/uji-linux-native.sh. Options: reps=$REPS baseline=$BASELINE matrix=$MATRIX_REPEATS mutation=$MUTATION_REPEATS starts=$STARTS force=$FORCE skip_perf=$SKIP_PERF
status.tsv              ok/FAILED per step
environment             logs/environment.log, docker-info.json, images.txt
security-tests.xml      pytest JUnit (Lampiran A 1-22, 24-26); logs/security-tests.log
logs/supervisor-matrix.log  access matrix A-E (Tabel 2), one block per repeat
channel-mutation.json   mutation analysis M2/M3 (bagian 4.1)
docker-start.csv        raw docker run --rm cost per image
performance/            jobs.csv, trials.csv, summary.json, tabel.md (Tabel 5-7)
console.log             everything printed during the run
EOF
cat "$OUT/status.tsv"
tar -czf "hasil-uji-linux/$NAME.tar.gz" -C hasil-uji-linux "$NAME"
echo
echo "Done. Send this file back: $(pwd)/hasil-uji-linux/$NAME.tar.gz"
grep -q FAILED "$OUT/status.tsv" && { echo "Some steps FAILED: see status.tsv and logs/ (the archive still contains everything)."; exit 1; }
exit 0
