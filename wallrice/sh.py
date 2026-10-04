"""Running other programs: never raises for a missing tool or a failure, returns (rc, stdout)."""
import shutil
import subprocess


def run(*cmd, timeout=30, input=None, env=None):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, input=input, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    return p.returncode, p.stdout if p.returncode == 0 else (p.stderr or p.stdout)


def has(tool):
    return shutil.which(tool) is not None
