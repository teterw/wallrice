// wallrice for GNOME Shell: the desktop takes its colours from the wallpaper.
//
// The wallrice program (https://github.com/teterw/wallrice) does the theming; this extension adds what
// only the Shell can do:
//   - animated wallpaper changes (grow from the pointer, wipe, wave, fade) instead of the plain fade;
//     wallrice calls Prepare(effect) on D-Bus just before it sets the new wallpaper;
//   - the islands top bar and the dock in the wallpaper's colours, from a stylesheet wallrice writes to
//     ~/.local/share/wallrice/gnome-shell.css, reloaded live whenever it changes.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Background from 'resource:///org/gnome/shell/ui/background.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {Bar} from './bar.js';
import {Dock} from './dock.js';
import {animateOut, makePlan} from './transition.js';

const DEV = GLib.getenv('WALLRICE_DEV') === '1';  // the test harness's private Shell only

const IFACE = `<node>
  <interface name="io.github.teterw.Wallrice">
    <method name="Prepare">
      <arg type="s" direction="in" name="effect"/>
      <arg type="d" direction="out" name="seconds"/>
    </method>
    <method name="Version">
      <arg type="s" direction="out" name="version"/>
    </method>
    <method name="Reload"/>
    ${DEV ? `<method name="DevScreenshot"><arg type="s" direction="in" name="path"/></method>
    <method name="DevEval"><arg type="s" direction="in" name="code"/><arg type="s" direction="out" name="result"/></method>` : ''}
  </interface>
</node>`;

export default class WallriceExtension extends Extension {
    enable() {
        this._dataDir = GLib.build_filenamev([GLib.get_user_data_dir(), 'wallrice']);
        this._cssFile = Gio.File.new_for_path(GLib.build_filenamev([this._dataDir, 'gnome-shell.css']));
        this._jsonFile = Gio.File.new_for_path(GLib.build_filenamev([this._dataDir, 'gnome-shell.json']));
        this._loaded = null;
        this._plan = null;
        this._timelines = new Set();

        this._patchBackground();
        // the picker opens and closes with its own zoom: the Shell's window animations would get in
        // the way of the seamless hand-over to the desktop
        global.display.connectObject('window-created', (_d, win) => this._skipEffects(win), this);
        this._bar = new Bar(args => this._runWallrice(args));
        this._bar.enable();
        this._dock = new Dock();
        this._dock.enable();
        this._monitors = [this._cssFile, this._jsonFile].map(f => {
            const m = f.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, null);
            m.connect('changed', () => this._reloadSoon());
            return m;
        });
        this._reload();

        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, '/io/github/teterw/Wallrice');
        if (DEV) {  // the test Shell: start on the desktop, not the overview
            if (Main.layoutManager._startingUp)
                this._startupId = Main.layoutManager.connect('startup-complete', () => Main.overview.hide());
            else
                Main.overview.hide();
        }
    }

    disable() {
        global.display.disconnectObject(this);
        if (this._startupId)
            Main.layoutManager.disconnect(this._startupId);
        this._startupId = 0;
        this._dbus?.unexport();
        this._dbus = null;
        this._monitors?.forEach(m => m.cancel());
        this._monitors = null;
        if (this._reloadId)
            GLib.source_remove(this._reloadId);
        this._reloadId = 0;
        this._timelines.forEach(t => t.stop());
        this._timelines.clear();
        this._unpatchBackground();
        this._dock?.disable();
        this._dock = null;
        this._bar?.disable();
        this._bar = null;
        this._unloadStylesheet();
    }

    // ---------------------------------------------------------------- D-Bus

    Prepare(effect) {
        this._plan = {...makePlan(effect, global.get_pointer()), until: GLib.get_monotonic_time() + 6e6};
        return this._plan.duration;
    }

    Version() {
        return this.metadata['version-name'] ?? String(this.metadata.version ?? '');
    }

    Reload() {
        this._reload();
    }

    DevEval(code) {
        if (!DEV)
            return '';
        try {
            // eslint-disable-next-line no-eval
            return String(eval(code));
        } catch (e) {
            return `ERR ${e}`;
        }
    }

    DevScreenshotAsync([path], invocation) {
        // answers only once the PNG is written, so the test harness's screenshots never overlap
        if (!DEV) {
            invocation.return_value(null);
            return;
        }
        const shot = new Shell.Screenshot();
        const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.NONE, null);
        shot.screenshot(false, stream, (o, res) => {
            try {
                o.screenshot_finish(res);
            } catch (e) {
                logError(e, 'wallrice: screenshot');
            }
            stream.close(null);
            invocation.return_value(null);
        });
    }

    // ---------------------------------------------------------------- transitions

    _patchBackground() {
        const proto = Background.BackgroundManager.prototype;
        const original = proto._swapBackgroundActor;
        const ext = this;
        this._originalSwap = original;
        proto._swapBackgroundActor = function () {
            const plan = ext._plan;
            if (!plan || GLib.get_monotonic_time() > plan.until)
                return original.call(this);  // a change wallrice didn't ask for: the Shell's own fade
            const old = this.backgroundActor;
            this.backgroundActor = this._newBackgroundActor;
            this._newBackgroundActor = null;
            this.emit('changed');
            if (plan.effect === 'none' || Main.layoutManager.screenTransition.visible) {
                old.destroy();  // the picker already animated this change
                return;
            }
            const monitor = Main.layoutManager.monitors[this._monitorIndex] ?? Main.layoutManager.primaryMonitor;
            try {
                const tl = animateOut(old, monitor, plan, t => ext._timelines.delete(t));
                ext._timelines.add(tl);
            } catch (e) {
                logError(e, 'wallrice: transition');
                old.destroy();
            }
        };
    }

    _unpatchBackground() {
        if (this._originalSwap)
            Background.BackgroundManager.prototype._swapBackgroundActor = this._originalSwap;
        this._originalSwap = null;
    }

    _skipEffects(win) {
        const ids = [win.get_gtk_application_id?.(), win.get_wm_class?.(), win.get_wm_class_instance?.()];
        if (!ids.some(id => id && id.startsWith('wallrice-picker')))
            return;
        const skip = () => {
            const actor = win.get_compositor_private();
            if (actor)
                Main.wm.skipNextEffect(actor);
        };
        skip();  // the map animation
        win.connectObject('unmanaging', skip, this);  // and the close animation
    }

    // ---------------------------------------------------------------- stylesheet and settings

    _reloadSoon() {
        if (this._reloadId)
            GLib.source_remove(this._reloadId);
        this._reloadId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            this._reloadId = 0;
            this._reload();
            return GLib.SOURCE_REMOVE;
        });
    }

    _reload() {
        let settings = {};
        try {
            const [, bytes] = this._jsonFile.load_contents(null);
            settings = JSON.parse(new TextDecoder().decode(bytes));
        } catch {
            settings = {};
        }
        this._dock?.setMono(settings.dock_mono !== false);
        if (!this._cssFile.query_exists(null)) {
            this._unloadStylesheet();
            return;
        }
        // St parses a stylesheet when it's loaded: unload the old copy and load the new file. The
        // theme context notices the change and every actor restyles at once.
        this._unloadStylesheet();
        const theme = St.ThemeContext.get_for_stage(global.stage).get_theme();
        try {
            theme.load_stylesheet(this._cssFile);
            this._loaded = this._cssFile;
        } catch (e) {
            logError(e, 'wallrice: stylesheet');
        }
    }

    _unloadStylesheet() {
        if (!this._loaded)
            return;
        St.ThemeContext.get_for_stage(global.stage).get_theme().unload_stylesheet(this._loaded);
        this._loaded = null;
    }

    // ---------------------------------------------------------------- the wallrice program

    _runWallrice(args) {
        const exe = [GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'wallrice']), 'wallrice']
            .find(p => p.includes('/') ? GLib.file_test(p, GLib.FileTest.IS_EXECUTABLE) : GLib.find_program_in_path(p));
        if (!exe) {
            Main.notify('wallrice', 'The wallrice program isn\'t installed: https://github.com/teterw/wallrice');
            return;
        }
        try {
            Gio.Subprocess.new([exe, ...args.split(' ')], Gio.SubprocessFlags.NONE);
        } catch (e) {
            logError(e, 'wallrice: launch');
        }
    }
}
