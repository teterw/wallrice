"""A fake command runner: an in-memory dconf (read/load/write/reset/dump) that records every call."""
import configparser

from helpers import fake_home  # noqa: F401


class FakeRun:
    def __init__(self, values=None, fail=()):
        self.values = dict(values or {})
        self.calls = []
        self.fail = set(fail)

    def __call__(self, *cmd, timeout=30, input=None, env=None):
        cmd = [str(c) for c in cmd]
        self.calls.append((cmd, input))
        if cmd[0] in self.fail:
            return 1, f"{cmd[0]}: failed"
        if cmd[0] == "dconf":
            op = cmd[1]
            if op == "read":
                v = self.values.get(cmd[2])
                return 0, (v + "\n") if v else ""
            if op == "load":
                cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
                cp.optionxform = str
                cp.read_string(input)
                for sec in cp.sections():
                    for k, v in cp[sec].items():
                        self.values[f"/{sec}/{k}"] = v
                return 0, ""
            if op == "write":
                self.values[cmd[2]] = cmd[3]
                return 0, ""
            if op == "reset":
                key = cmd[-1]
                if "-f" in cmd:
                    for k in [k for k in self.values if k.startswith(key)]:
                        del self.values[k]
                else:
                    self.values.pop(key, None)
                return 0, ""
            if op == "dump":
                return 0, "[org/gnome/desktop/interface]\ngtk-theme='Adwaita'\n"
        if cmd[0] == "gdbus":
            return 1, "no such object"
        return 0, ""

    def loads(self):
        return [inp for cmd, inp in self.calls if cmd[:2] == ["dconf", "load"]]


def tools(*names):
    names = set(names)
    return lambda t: f"/usr/bin/{t}" if t in names else None
