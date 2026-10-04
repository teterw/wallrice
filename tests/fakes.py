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
        if cmd[0] == "xfconf-query":
            return self.xfconf(cmd[1:])
        if cmd[0] in ("kreadconfig6", "kreadconfig5"):
            key = f"kde:{cmd[cmd.index('--group') + 1]}:{cmd[cmd.index('--key') + 1]}"
            return 0, self.values.get(key, "")
        if cmd[0] == "plasma-apply-colorscheme":
            self.values["kde:General:ColorScheme"] = cmd[-1]
            return 0, ""
        if cmd[:2] == ["hyprctl", "cursorpos"]:
            return 0, "100, 200"
        if cmd[0] == "pgrep":
            return 1, ""
        return 0, ""

    def xfconf(self, args):
        ch = args[args.index("-c") + 1]
        if "-l" in args:
            keys = sorted(k.split(":", 2)[2] for k in self.values if k.startswith(f"xfconf:{ch}:"))
            if "-v" in args:
                return 0, "\n".join(f"{k} {self.values[f'xfconf:{ch}:{k}']}" for k in keys)
            return 0, "\n".join(keys)
        prop = args[args.index("-p") + 1]
        key = f"xfconf:{ch}:{prop}"
        if "-r" in args:
            self.values.pop(key, None)
            return 0, ""
        if "-s" in args:
            self.values[key] = args[args.index("-s") + 1]
            return 0, ""
        return (0, self.values[key]) if key in self.values else (1, "no such property")

    def ran(self, name):
        """Every call of this program, as argument lists."""
        return [cmd for cmd, _ in self.calls if cmd[0] == name]

    def loads(self):
        return [inp for cmd, inp in self.calls if cmd[:2] == ["dconf", "load"]]


def tools(*names):
    names = set(names)
    return lambda t: f"/usr/bin/{t}" if t in names else None
