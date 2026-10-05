"""One lock for every job that writes to the repo (the daily episode and the backfill).

    with repolock.hold("daily", wait_minutes=90): ...

A lock whose owner process has died is treated as stale and taken over.
"""
import contextlib, ctypes, datetime, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "logs", "repo.lock")


class Busy(Exception):
    pass


def _alive(pid):
    if sys.platform == "win32":
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def holder():
    try:
        return json.load(open(LOCK, encoding="utf-8"))
    except (OSError, ValueError):
        return None


@contextlib.contextmanager
def hold(owner, wait_minutes=0, log=print):
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    deadline = time.time() + wait_minutes * 60
    announced = False
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"owner": owner, "pid": os.getpid(),
                           "since": datetime.datetime.now().isoformat(timespec="seconds")}, f)
            break
        except FileExistsError:
            h = holder()
            if h and not _alive(h.get("pid", -1)):
                log(f"removing stale lock left by {h.get('owner')} (pid {h.get('pid')})")
                os.remove(LOCK)
                continue
            if time.time() >= deadline:
                raise Busy(f"repo is locked by {h.get('owner') if h else '?'} since {h.get('since') if h else '?'}")
            if not announced:
                log(f"repo locked by {h.get('owner') if h else '?'}; waiting up to {wait_minutes} minutes")
                announced = True
            time.sleep(30)
    try:
        yield
    finally:
        h = holder()
        if h and h.get("pid") == os.getpid():
            os.remove(LOCK)
