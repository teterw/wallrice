// The Extensions app's settings button: shortcuts to wallrice's own screens.
import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

function wallrice(args) {
    const exe = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'wallrice']);
    try {
        Gio.Subprocess.new([GLib.file_test(exe, GLib.FileTest.IS_EXECUTABLE) ? exe : 'wallrice', ...args],
            Gio.SubprocessFlags.NONE);
    } catch (e) {
        console.error(`wallrice: ${e.message}`);
    }
}

export default class WallricePrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage({title: 'wallrice', icon_name: 'preferences-desktop-wallpaper-symbolic'});
        const group = new Adw.PreferencesGroup({
            title: 'wallrice',
            description: 'The desktop takes its colours from the wallpaper. These open wallrice\'s own screens.',
        });
        for (const [title, subtitle, args] of [
            ['Top bar style', 'Nine styles, previewed live on your top bar', ['bar']],
            ['Wallpapers', 'Pick a wallpaper (Super+W)', ['pick']],
            ['Review wallpapers', 'Keep or remove each downloaded wallpaper', ['walls', 'review']],
        ]) {
            const row = new Adw.ActionRow({title, subtitle, activatable: true});
            row.add_suffix(new Gtk.Image({icon_name: 'go-next-symbolic'}));
            row.connect('activated', () => wallrice(args));
            group.add(row);
        }
        page.add(group);
        window.add(page);
    }
}
