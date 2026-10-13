#!/usr/bin/env python3
"""cron 双跑去重补丁校验 — 检查 manager.py 是否有 O_CREAT|O_EXCL 锁文件去重补丁。

pod 重建会覆盖 site-packages，本脚本自动补回。

输出：
  "校验通过" — 补丁在位
  "CRON_DEDUP_REPAIRED" — 补丁丢失已自动补回（需重启进程生效）
  "CRON_DEDUP_LOST" — 补丁丢失且自动补回失败（框架改了代码结构，需手动处理）

环境变量：
  QWENPAW_SITE_PACKAGES  site-packages 路径（默认 /app/venv/lib/python3.11/site-packages）
  QWENPAW_WORKING        working 目录（默认 /app/working）
"""
import os
import sys

SITE_PACKAGES = os.environ.get(
    "QWENPAW_SITE_PACKAGES",
    "/app/venv/lib/python3.11/site-packages",
)
WORKING = os.environ.get("QWENPAW_WORKING", "/app/working")
MANAGER_PY = os.path.join(SITE_PACKAGES, "qwenpaw/app/crons/manager.py")
PATCH_MARKER = "cron dedup"

PATCHED_METHOD = '''    async def _scheduled_callback(self, job_id: str) -> None:
        # ── 跨进程去重补丁 ──
        # 多个 pod 共享同一存储，各自一套 scheduler 导致同一 cron 双跑。
        # 用 O_CREAT|O_EXCL 在共享目录抢锁文件，抢到才跑，超时防死锁。
        import os as _os, time as _time
        _DEDUP_DIR = Path("''' + WORKING + '''") / "cron_dedup"
        try:
            _DEDUP_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        _LOCK = _DEDUP_DIR / f"{job_id}.lock"
        _STALE = 300
        _got_lock = False
        try:
            fd = _os.open(str(_LOCK), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY, 0o644)
            _os.write(fd, str(_time.time()).encode())
            _os.close(fd)
            _got_lock = True
        except FileExistsError:
            try:
                _age = _time.time() - _os.path.getmtime(str(_LOCK))
            except OSError:
                _age = 999
            if _age < _STALE:
                logger.info("cron dedup: skipping %s (lock held, %.1fs)", job_id, _age)
                return
            try:
                _os.unlink(str(_LOCK))
                fd = _os.open(str(_LOCK), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY, 0o644)
                _os.write(fd, str(_time.time()).encode())
                _os.close(fd)
                _got_lock = True
            except OSError:
                logger.warning("cron dedup: reclaim failed for %s, skipping", job_id)
                return
        except OSError:
            logger.warning("cron dedup: lock error for %s, proceeding without lock", job_id)
            _got_lock = False

        try:
            job = await self._repo.get_job(job_id)
            if not job:
                return
            if self._requires_portability_review(job):
                await self._record_skipped(
                    job,
                    "Imported cron job is awaiting explicit promotion",
                )
                return

            await self._execute_once(
                job,
                trigger="scheduled",
            )

            aps_job = self._scheduler.get_job(job_id)
            st = self._states.get(job_id, CronJobState())
            st.next_run_at = aps_job.next_run_time if aps_job else None
            self._states[job_id] = st
        finally:
            pass
'''


def main():
    if not os.path.isfile(MANAGER_PY):
        print("CRON_DEDUP_LOST")
        print(f"  manager.py not found at {MANAGER_PY}", file=sys.stderr)
        sys.exit(1)

    with open(MANAGER_PY, "r", encoding="utf-8") as f:
        src = f.read()

    if PATCH_MARKER in src:
        print("校验通过")
        sys.exit(0)

    method_start = src.find("    async def _scheduled_callback(self, job_id: str) -> None:")
    if method_start < 0:
        print("CRON_DEDUP_LOST")
        print("  cannot find _scheduled_callback in manager.py", file=sys.stderr)
        sys.exit(1)

    search_from = method_start + 1
    next_def = -1
    for marker in ["    async def ", "    def ", "    @staticmethod", "    @property"]:
        idx = src.find(marker, search_from)
        if idx >= 0 and (next_def < 0 or idx < next_def):
            next_def = idx
    if next_def < 0:
        next_def = len(src)

    patched_src = src[:method_start] + PATCHED_METHOD + "\n" + src[next_def:]

    bak = MANAGER_PY + ".bak-cron-dedup-" + os.popen("date +%Y%m%d").read().strip()
    os.system(f"cp {MANAGER_PY} {bak}")

    with open(MANAGER_PY, "w", encoding="utf-8") as f:
        f.write(patched_src)

    import subprocess
    r = subprocess.run(["python3", "-m", "py_compile", MANAGER_PY], capture_output=True, text=True)
    if r.returncode != 0:
        os.system(f"cp {bak} {MANAGER_PY}")
        print("CRON_DEDUP_LOST")
        print(f"  py_compile failed: {r.stderr[:200]}", file=sys.stderr)
        sys.exit(1)

    with open(MANAGER_PY, "r", encoding="utf-8") as f:
        verify = f.read()
    if PATCH_MARKER not in verify:
        print("CRON_DEDUP_LOST")
        print("  patch insertion failed", file=sys.stderr)
        sys.exit(1)

    print("CRON_DEDUP_REPAIRED")
    print(f"  backup: {bak}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
