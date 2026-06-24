# Iter1 — Slurm + psana2 recon on S3DF `milano` (for CI runner)

**Date:** 2026-06-24  **Remote:** sdfiana025 (login/interactive), user `cwang31`, via cc-bridge `ci-confluence`.
**Verdict:** The `salloc --no-shell` + `srun --jobid` + `scancel` dev pattern WORKS on milano. One-shot `sbatch` WORKS. psana2 imports cleanly on a milano compute node. No blockers — only minor gotchas (below).

---

## 1. Milano partition (verified)

```
sinfo -p milano -o "%P %a %l %D %t %c %m %f"
```

| Property | Value |
|----------|-------|
| Partition | `milano` (AVAIL `up`) |
| Max TimeLimit | **10-00:00:00** (10 days) |
| Per-node CPUs | **128** physical |
| Per-node usable (exclusive) | **120 CPUs** (QOS/system reserves ~8) |
| Per-node memory | **480 GB** (`MEMORY=491520` MB; `free -g` ≈ 503 GB total) |
| Node count | ~272 nodes total; a few "fat" nodes have 1920 GB RAM |
| GPU | none |
| CPU | AMD EPYC 7713 (Milan), 2.00 GHz, RHEL 8.6 |
| Default constraint | `OS_VER:8.6` (auto-applied; salloc/sbatch print an info line about it) |

**Availability at recon time:** the partition is BUSY — typically only ~1 node truly `idle`, ~31 `mix`. With `--exclusive` you wait in the queue for a whole node to free up. In testing, pending → running took **5–15 s** (fast), but this is not guaranteed; a CI job requesting `--exclusive` may queue longer at peak. Consider whether the CI really needs `--exclusive` or could share a node with `--cpus-per-task=N --mem=NG`.

**Account:** `lcls:prjdat21` is valid and usable for submission. `slurmdbd` is **UP** (`sshare -A lcls:prjdat21` and `sacct` both respond; Slurm 24.11.3). If slurmdbd ever goes down, `sacct`/`sshare` break but `sbatch`/`sinfo`/`squeue`/`salloc` keep working.

---

## 2. Persistent dev allocation (salloc --no-shell + srun) — VERIFIED

Request the node ONCE (returns a job id, no interactive shell, allocation persists):

```bash
salloc --no-shell \
  --partition=milano --account=lcls:prjdat21 \
  --exclusive --mem=0 --time=00:20:00 -J ci-recon
# -> "salloc: Granted job allocation <JID>"; node e.g. sdfmilan180
```

Capture the JID from `squeue -u $USER` or the salloc stderr. Then run work steps against it:

```bash
JID=<jobid>

srun --jobid=$JID hostname                       # -> sdfmilanNNN (NOT sdfiana025)
srun --jobid=$JID bash -lc "nproc; free -g"       # default srun = 1 task -> nproc shows 16!
# To actually use all cores in one step, ask for them explicitly:
srun --jobid=$JID --cpus-per-task=120 --cpu-bind=none bash -lc "nproc"   # -> 120

# psana2 activation on the milano node:
srun --jobid=$JID bash -lc \
  "source /sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh && \
   which python && python -c 'import psana; print(\"psana OK\", psana.__file__)'"
```

Clean up (release the exclusive node):

```bash
scancel $JID
squeue -u $USER     # confirm empty
```

**Verified results:**
- `salloc --no-shell` granted job 29758245 on sdfmilan180, persisted with no shell. ✓
- `srun --jobid` landed on **sdfmilan180** (the compute node), not sdfiana025. ✓
- `scontrol show job` reported `AllocTRES=cpu=120,mem=480G,node=1` → whole node granted via `--exclusive --mem=0`. ✓
- `scancel` released it; `squeue -u cwang31` returned empty. ✓

---

## 3. One-shot batch job (sbatch) — VERIFIED

```bash
#!/bin/bash
#SBATCH --partition=milano
#SBATCH --account=lcls:prjdat21
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=00:05:00
#SBATCH --job-name=ci-recon-batch
#SBATCH --output=/path/to/notes/ci-smoke-%j.out
set -eo pipefail            # IMPORTANT: NO -u (see gotcha 3)
echo "host=$(hostname) nproc=$(nproc)"
source /sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh
python --version
python -c "import psana; print('psana OK', psana.__file__)"
```

Submit and capture a clean job id (redirect stderr so the OS_VER info line doesn't pollute `--parsable`):

```bash
JID=$(sbatch --parsable myjob.sbatch 2>/dev/null)
```

**Verified:** job 29758332 ran on sdfmilan231, `nproc=120`, psana2 imported, exit rc=0.

---

## 4. psana2 activation recipe (VERIFIED on milano compute node)

```bash
source /sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh
```

| Item | Value (verified on sdfmilan180 / sdfmilan231) |
|------|-----------------------------------------------|
| Release dir | `/sdf/group/lcls/ds/ana/sw/conda2/rel/lcls2_041726` |
| Conda env | `ps_20241122` |
| python | `/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps_20241122/bin/python` |
| python version | **3.9.20** |
| psana | `.../rel/lcls2_041726/install/lib/python3.9/site-packages/psana/__init__.py` |
| psana flavor | **psana2 confirmed** (`psana.psexp` module present; `psana.DataSource` present) |

This is the LCLS2/psana2 stack (single env, no module load needed). Activation works identically on the milano compute node and the login node.

---

## 5. Fixture data visibility — VERIFIED

```bash
ls -d /sdf/data/lcls/ds/prj/public01/xtc
# -> /sdf/data/lcls/ds/prj/public01/xtc   (visible from the milano compute node)
```

The `/sdf/data/...` GPFS/weka mounts are visible from compute nodes, so CI fixtures and the workspace (`/sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence`) are reachable from inside jobs. No staging needed.

---

## 6. Gotchas / notes

1. **120 usable cores, not 128.** `--exclusive` grants `AllocTRES=cpu=120` even though `lscpu` shows 128. `--cpus-per-task=128` fails with `More processors requested than permitted`. Use **120** as the max for `--cpus-per-task` / parallelism.

2. **Default `srun` sees only 1 core's worth.** A bare `srun --jobid=$JID bash -lc "nproc"` reports `16` (default 1 task, partial binding), NOT the full node. For full-node steps add `--cpus-per-task=120 --cpu-bind=none`. The allocation itself still holds all 120 cores; this only affects what a single step is bound to.

3. **psconda is NOT `set -u` clean.** Sourcing `psconda.sh` under `set -u` dies with `ADDR2LINE: unbound variable` (from conda `activate.d/activate-binutils_linux-64.sh`). In CI scripts use `set -eo pipefail` (drop `-u`), OR `set +u` around the `source` line. This bit the first sbatch attempt.

4. **`sbatch --parsable` gets polluted by the OS_VER info line.** Slurm prints `No OS_VER constraint specified. Defaulting to OS_VER:8.6...` to **stderr** on every milano submit. Capture the job id with `2>/dev/null`: `JID=$(sbatch --parsable job.sbatch 2>/dev/null)`. Same line appears on `salloc` (harmless there).

5. **Partition is busy.** Only ~1 idle node at recon time. `--exclusive` requests queue until a full node frees. Queue wait was 5–15 s in testing but is not guaranteed at peak. If CI latency matters, consider non-exclusive (`--cpus-per-task=N --mem=NG`) to pack onto `mix` nodes.

6. **Time limit** for milano is 10 days max; use a short `--time` (e.g. `00:20:00` dev, `00:05:00` smoke) so a forgotten exclusive allocation doesn't hog a node.

7. **slurmdbd is up now** (Slurm 24.11.3). If it goes down, `sacct`/`sshare` break but submission/scheduling are unaffected.

---

## 7. Copy-paste TL;DR

```bash
# --- persistent dev node ---
salloc --no-shell --partition=milano --account=lcls:prjdat21 --exclusive --mem=0 --time=00:20:00 -J ci-dev
JID=$(squeue -u $USER -h -o "%i" -n ci-dev | head -1)
srun --jobid=$JID hostname
srun --jobid=$JID --cpus-per-task=120 --cpu-bind=none bash -lc 'set -eo pipefail; source /sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh; python -c "import psana; print(psana.__file__)"'
scancel $JID

# --- one-shot batch ---
JID=$(sbatch --parsable myjob.sbatch 2>/dev/null)   # myjob.sbatch: set -eo pipefail (NO -u)
```
