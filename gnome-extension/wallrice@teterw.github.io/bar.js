// The islands top bar. Left to right: workspaces 1-4, launchers, the focused window's title in the
// centre, then cpu/mem/net (Vitals' own when it's installed), the system indicators (volume, battery,
// wifi), the clock, and a notification bell. Each is a panel button, and the generated stylesheet makes
// every panel button an island in the wallpaper's colours. disable() puts the Shell's own bar back.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const WORKSPACES = 4;

const Workspaces = GObject.registerClass(
class WallriceWorkspaces extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'wallrice workspaces', true);
        this._box = new St.BoxLayout({style_class: 'wallrice-ws', y_align: Clutter.ActorAlign.CENTER});
        this.add_child(this._box);
        this._dots = [];
        for (let i = 0; i < WORKSPACES; i++) {
            const dot = new St.Button({
                style_class: 'wallrice-ws-dot', label: `${i + 1}`, y_align: Clutter.ActorAlign.CENTER,
            });
            dot.connect('clicked', () => this._activate(i));
            this._box.add_child(dot);
            this._dots.push(dot);
        }
        const wm = global.workspace_manager;
        wm.connectObject('active-workspace-changed', () => this._sync(),
            'notify::n-workspaces', () => this._sync(), this);
        global.display.connectObject('window-created', () => this._later(), this);
        global.window_manager.connectObject('switch-workspace', () => this._sync(),
            'destroy', () => this._later(), this);
        this.connect('scroll-event', (_a, event) => {
            const dir = event.get_scroll_direction();
            const d = dir === Clutter.ScrollDirection.UP || dir === Clutter.ScrollDirection.LEFT ? -1
                : dir === Clutter.ScrollDirection.DOWN || dir === Clutter.ScrollDirection.RIGHT ? 1 : 0;
            if (d)
                this._activate(wm.get_active_workspace_index() + d);
            return Clutter.EVENT_STOP;
        });
        this._sync();
    }

    _later() {
        if (!this._idle) {
            this._idle = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                this._idle = 0;
                this._sync();
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _activate(i) {
        const wm = global.workspace_manager;
        i = Math.max(0, Math.min(WORKSPACES - 1, i));
        while (i >= wm.n_workspaces && wm.n_workspaces < WORKSPACES)
            wm.append_new_workspace(false, global.get_current_time());
        const ws = wm.get_workspace_by_index(Math.min(i, wm.n_workspaces - 1));
        ws?.activate(global.get_current_time());
    }

    _sync() {
        const wm = global.workspace_manager;
        const active = wm.get_active_workspace_index();
        this._dots.forEach((dot, i) => {
            const ws = i < wm.n_workspaces ? wm.get_workspace_by_index(i) : null;
            const busy = ws ? ws.list_windows().some(w => !w.skip_taskbar) : false;
            if (i === active)
                dot.add_style_class_name('active');
            else
                dot.remove_style_class_name('active');
            if (busy)
                dot.add_style_class_name('busy');
            else
                dot.remove_style_class_name('busy');
        });
    }

    destroy() {
        if (this._idle)
            GLib.source_remove(this._idle);
        this._idle = 0;
        super.destroy();
    }
});

const Launchers = GObject.registerClass(
class WallriceLaunchers extends PanelMenu.Button {
    _init(wallrice, mono) {
        super._init(0.0, 'wallrice launchers', true);
        this._wallrice = wallrice;
        this._mono = mono;
        this._box = new St.BoxLayout({style_class: 'wallrice-launchers', y_align: Clutter.ActorAlign.CENTER});
        this.add_child(this._box);
        this._favs = AppFavorites.getAppFavorites();
        this._favs.connectObject('changed', () => this._build(), this);
        this._build();
    }

    _button(gicon, iconName, onClick, tip) {
        const icon = new St.Icon({style_class: 'wallrice-launcher-icon', icon_size: 16});
        if (gicon)
            icon.gicon = gicon;
        else
            icon.icon_name = iconName;
        const b = new St.Button({style_class: 'wallrice-launcher', child: icon, y_align: Clutter.ActorAlign.CENTER,
            accessible_name: tip});
        b.connect('clicked', onClick);
        return b;
    }

    setMono(mono) {
        if (mono === this._mono)
            return;
        this._mono = mono;
        this._build();
    }

    _build() {
        this._box.destroy_all_children();
        for (const app of this._favs.getFavorites().slice(0, 3)) {
            // flat monochrome (taskbar-icons on): the app's symbolic icon when the icon theme has one
            const name = app.app_info?.get_icon()?.to_string?.() ?? '';
            const gicon = this._mono && name && !name.includes('/')
                ? Gio.ThemedIcon.new_from_names([`${name}-symbolic`, name])
                : app.get_icon();
            this._box.add_child(this._button(gicon, null, () => app.activate(), app.get_name()));
        }
        this._box.add_child(this._button(null, this._mono ? 'preferences-desktop-wallpaper-symbolic'
            : 'preferences-desktop-wallpaper', () => this._wallrice('pick'), 'Wallpapers'));
    }

});

const Title = GObject.registerClass(
class WallriceTitle extends PanelMenu.Button {
    _init() {
        super._init(0.5, 'wallrice title', true);
        this._label = new St.Label({style_class: 'wallrice-title', y_align: Clutter.ActorAlign.CENTER});
        this._label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this.add_child(this._label);
        this.reactive = false;
        this._win = null;
        global.display.connectObject('notify::focus-window', () => this._track(), this);
        this._track();
    }

    _track() {
        this._win?.disconnectObject(this);
        this._win = global.display.focus_window;
        this._win?.connectObject('notify::title', () => this._sync(),
            'unmanaged', () => this._track(), this);
        this._sync();
    }

    _sync() {
        const w = this._win;
        const title = w && !w.skip_taskbar ? (w.get_title() || '') : '';
        const app = w ? Shell.WindowTracker.get_default().get_window_app(w) : null;
        const text = title || app?.get_name() || '';
        this._label.text = text;
        this.visible = text.length > 0;
        this._label.style = `max-width: ${Math.round(Main.layoutManager.primaryMonitor.width * 0.32)}px;`;
    }

    destroy() {
        this._win?.disconnectObject(this);
        this._win = null;
        super.destroy();
    }
});

function readFile(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(bytes) : '';
    } catch {
        return '';
    }
}

function human(bytes) {
    const units = ['B', 'K', 'M', 'G'];
    let i = 0;
    while (bytes >= 1000 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes >= 10 || i === 0 ? Math.round(bytes) : bytes.toFixed(1)}${units[i]}`;
}

const Stats = GObject.registerClass(
class WallriceStats extends PanelMenu.Button {
    _init() {
        super._init(0.5, 'wallrice stats', true);
        const box = new St.BoxLayout({y_align: Clutter.ActorAlign.CENTER});
        this.add_child(box);
        this._labels = {};
        for (const key of ['cpu', 'mem', 'net']) {
            box.add_child(new St.Label({text: `${key} `, style_class: 'wallrice-stats-key', y_align: Clutter.ActorAlign.CENTER}));
            this._labels[key] = new St.Label({text: '…', style_class: 'wallrice-stats-value', y_align: Clutter.ActorAlign.CENTER});
            box.add_child(this._labels[key]);
        }
        this._prev = null;
        this._update();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_LOW, 2, () => {
            this._update();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _update() {
        const cpu = readFile('/proc/stat').split('\n')[0].trim().split(/\s+/).slice(1).map(Number);
        const idle = cpu[3] + (cpu[4] || 0);
        const total = cpu.reduce((a, b) => a + b, 0);
        const mem = Object.fromEntries(readFile('/proc/meminfo').split('\n').filter(Boolean)
            .map(l => [l.split(':')[0], parseInt(l.split(':')[1])]));
        let rx = 0, tx = 0;
        for (const line of readFile('/proc/net/dev').split('\n').slice(2)) {
            const [name, rest] = line.split(':');
            if (!rest || name.trim() === 'lo')
                continue;
            const f = rest.trim().split(/\s+/).map(Number);
            rx += f[0];
            tx += f[8];
        }
        const now = GLib.get_monotonic_time() / 1e6;
        if (this._prev) {
            const dt = Math.max(0.5, now - this._prev.now);
            const busy = 1 - (idle - this._prev.idle) / Math.max(1, total - this._prev.total);
            this._labels.cpu.text = `${Math.round(Math.max(0, busy) * 100)}%`;
            this._labels.net.text = `${human((rx - this._prev.rx + tx - this._prev.tx) / dt)}`;
        }
        const usedKiB = (mem.MemTotal || 0) - (mem.MemAvailable || 0);
        this._labels.mem.text = human(usedKiB * 1024);
        this._prev = {idle, total, rx, tx, now};
    }

    destroy() {
        GLib.source_remove(this._timer);
        super.destroy();
    }
});

const Bell = GObject.registerClass(
class WallriceBell extends PanelMenu.Button {
    _init(dateMenu) {
        super._init(0.5, 'wallrice notifications', true);
        this.add_style_class_name('wallrice-bell');
        this._icon = new St.Icon({icon_name: 'preferences-system-notifications-symbolic', style_class: 'system-status-icon'});
        this.add_child(this._icon);
        this._dateMenu = dateMenu;
        dateMenu?._indicator?.connectObject('notify::visible', () => this._sync(), this);
        this._sync();
    }

    _sync() {
        if (this._dateMenu?._indicator?.visible)
            this.add_style_class_name('unread');
        else
            this.remove_style_class_name('unread');
    }

    vfunc_event(event) {
        const t = event.type();
        if (t === Clutter.EventType.BUTTON_RELEASE || t === Clutter.EventType.TOUCH_END) {
            this._dateMenu?.menu.toggle();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

});

export class Bar {
    constructor(runWallrice, mono = true) {
        this._run = runWallrice;
        this._mono = mono;
        this._items = [];
    }

    setMono(mono) {
        this._mono = mono;
        this._launchers?.setMono(mono);
    }

    enable() {
        const panel = Main.panel;
        panel.add_style_class_name('wallrice-panel');
        this._activities = panel.statusArea.activities;
        this._activities?.container.hide();
        this._add('wallrice-workspaces', new Workspaces(), 0, 'left');
        this._launchers = new Launchers(this._run, this._mono);
        this._add('wallrice-launchers', this._launchers, 1, 'left');

        // the clock moves to the right; the window title takes the centre
        const dm = panel.statusArea.dateMenu;
        if (dm) {
            const c = dm.container;
            this._dmParent = c.get_parent();
            this._dmIndex = this._dmParent?.get_children().indexOf(c) ?? -1;
            this._dmParent?.remove_child(c);
            panel._rightBox.add_child(c);
            dm.add_style_class_name('wallrice-clock');
        }
        this._add('wallrice-title', new Title(), 0, 'center');
        if (!panel.statusArea.vitalsMenu)
            this._add('wallrice-stats', new Stats(), 0, 'right');
        this._add('wallrice-bell', new Bell(dm), panel._rightBox.get_n_children(), 'right');
    }

    _add(role, button, index, box) {
        Main.panel.addToStatusArea(role, button, index, box);
        this._items.push(button);
    }

    disable() {
        const panel = Main.panel;
        this._items.forEach(b => b.destroy());
        this._items = [];
        this._launchers = null;
        const dm = panel.statusArea.dateMenu;
        if (dm && this._dmParent) {
            const c = dm.container;
            c.get_parent()?.remove_child(c);
            this._dmParent.insert_child_at_index(c, Math.max(0, this._dmIndex));
            dm.remove_style_class_name('wallrice-clock');
        }
        this._dmParent = null;
        this._activities?.container.show();
        panel.remove_style_class_name('wallrice-panel');
    }
}
