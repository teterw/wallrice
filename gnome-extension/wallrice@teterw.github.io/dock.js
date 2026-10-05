// Dash to Dock / Ubuntu Dock in wallrice's look: the generated stylesheet colours the floating dock, and
// this makes its app icons flat and monochrome (each can be turned off) (a desaturate effect on each icon, so the accent-coloured
// running dots keep their colour). Docks are found as they appear: Dash to Dock may load after wallrice
// and rebuilds its dock when its settings change.
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const NAME = 'dashtodockContainer';
const EFFECT = 'wallrice-mono';

function* walk(actor) {
    yield actor;
    for (const child of actor.get_children())
        yield* walk(child);
}

export class Dock {
    constructor() {
        this._mono = true;
        this._styled = true;
        this._docks = new Map();  // container -> [signal ids on its dash box]
        this._uiId = 0;
        this._later = 0;
    }

    enable() {
        this._uiId = Main.uiGroup.connect('child-added', () => this._soon());
        // Dash to Dock rebuilds its icons when the theme changes: repaint before that frame is drawn
        this._themeId = St.ThemeContext.get_for_stage(global.stage).connect('changed', () => this._soon());
        this._scan();
    }

    /** styled: the dock in the theme's colours (`wallrice on|off dock`); mono: flat monochrome app
     * icons (`wallrice on|off taskbar-icons`). */
    configure({styled = true, mono = true} = {}) {
        this._styled = styled;
        this._mono = mono;
        this._scan();
    }

    _soon() {
        if (this._later)
            return;
        this._later = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._later = 0;
            this._scan();
            return false;
        });
    }

    _scan() {
        for (const actor of Main.uiGroup.get_children()) {
            if (actor.name !== NAME)
                continue;
            if (!this._docks.has(actor)) {
                const box = actor.dash?._box;
                const ids = box ? [box.connect('child-added', () => this._soon())] : [];
                ids.destroyId = actor.connect('destroy', () => this._docks.delete(actor));
                this._docks.set(actor, ids);
            }
            if (this._styled)
                actor.add_style_class_name('wallrice-dock');
            else
                actor.remove_style_class_name('wallrice-dock');
            this._paint(actor);
        }
    }

    _paint(container) {
        for (const actor of walk(container)) {
            // An app icon (BaseIcon, ".overview-icon") draws its picture in its _iconBin: the effect
            // goes there, so it's in place even before a rebuilt icon gets its picture, and the
            // running dots (drawn outside the bin) keep the accent colour.
            let a = null;
            if (actor.has_style_class_name?.('overview-icon'))
                a = actor._iconBin ?? null;
            else if (actor instanceof St.Icon && !actor.get_parent()?.get_parent()?.has_style_class_name?.('overview-icon'))
                a = actor;
            if (!a)
                continue;
            const has = a.get_effect(EFFECT);
            if (this._mono && !has)
                a.add_effect_with_name(EFFECT, new Clutter.DesaturateEffect({factor: 1.0}));
            else if (!this._mono && has)
                a.remove_effect_by_name(EFFECT);
        }
    }

    disable() {
        if (this._uiId)
            Main.uiGroup.disconnect(this._uiId);
        this._uiId = 0;
        if (this._themeId)
            St.ThemeContext.get_for_stage(global.stage).disconnect(this._themeId);
        this._themeId = 0;
        if (this._later)
            global.compositor.get_laters().remove(this._later);
        this._later = 0;
        for (const [actor, ids] of this._docks) {
            const box = actor.dash?._box;
            ids.forEach(id => box?.disconnect(id));
            actor.disconnect(ids.destroyId);
            actor.remove_style_class_name('wallrice-dock');
            this._mono = false;
            this._paint(actor);
        }
        this._docks.clear();
    }
}
