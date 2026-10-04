// swww-style wallpaper changes for GNOME Shell. The Shell cross-fades a new wallpaper by easing the old
// picture's opacity (BackgroundManager._swapBackgroundActor); wallrice instead puts a shader on the old
// picture that reveals the new one underneath: a soft circle growing from the pointer, a soft straight
// edge wiping across at an angle, a rippling wave, or a fade. Everything runs on the GPU in the
// compositor, so it's smooth and works on Wayland.
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

export const EFFECTS = ['grow', 'wipe', 'wave', 'fade'];
const MODES = {grow: 0, wipe: 1, wave: 2, fade: 3};
const ANGLES = [15, 165, 195, 345, 60, 240];

const DECLARATIONS = `
uniform float progress;
uniform vec2 origin;
uniform vec2 size;
uniform float mode;
uniform float angle;
uniform float soft;
`;

// How much of the OLD picture stays at this pixel (1 = old, 0 = the new one shows through).
const CODE = `
vec2 p = cogl_tex_coord_in[0].st * size;
float keep = 1.0;
vec2 dir = vec2(cos(angle), sin(angle));
float c0 = 0.0;
float c1 = dot(vec2(size.x, 0.0), dir);
float c2 = dot(vec2(0.0, size.y), dir);
float c3 = dot(size, dir);
float lo = min(min(c0, c1), min(c2, c3));
float hi = max(max(c0, c1), max(c2, c3));
if (mode < 0.5) {
    float maxr = max(max(distance(origin, vec2(0.0)), distance(origin, vec2(size.x, 0.0))),
                     max(distance(origin, vec2(0.0, size.y)), distance(origin, size)));
    float r = progress * (maxr + soft);
    keep = smoothstep(r - soft, r, distance(p, origin));
} else if (mode < 1.5) {
    float s = lo + progress * (hi - lo + soft);
    keep = smoothstep(s - soft, s, dot(p, dir));
} else if (mode < 2.5) {
    vec2 nrm = vec2(-dir.y, dir.x);
    float amp = 0.04 * min(size.x, size.y);
    float lam = 0.25 * max(size.x, size.y);
    float s = lo - 2.0 * amp + progress * (hi - lo + 4.0 * amp + soft);
    float edge = s + amp * sin(6.2831853 * dot(p, nrm) / lam + progress * 7.0);
    keep = smoothstep(edge - soft * 0.25, edge, dot(p, dir));
} else {
    keep = 1.0 - progress;
}
cogl_color_out *= keep;
`;

// GNOME 48 moved the snippet hooks from Shell to Cogl
const Hook = (Cogl.SnippetHook ?? Shell.SnippetHook).FRAGMENT;

export const TransitionEffect = GObject.registerClass(
class WallriceTransitionEffect extends Shell.GLSLEffect {
    _init(params) {
        super._init(params);
        this._loc = {};
        for (const name of ['progress', 'origin', 'size', 'mode', 'angle', 'soft'])
            this._loc[name] = this.get_uniform_location(name);
    }

    vfunc_build_pipeline() {
        this.add_glsl_snippet(Hook, DECLARATIONS, CODE, false);
    }

    setup({mode, origin, size, angle, soft}) {
        this.set_uniform_float(this._loc.mode, 1, [mode]);
        this.set_uniform_float(this._loc.origin, 2, origin);
        this.set_uniform_float(this._loc.size, 2, size);
        this.set_uniform_float(this._loc.angle, 1, [angle]);
        this.set_uniform_float(this._loc.soft, 1, [soft]);
        this.setProgress(0);
    }

    setProgress(t) {
        this.set_uniform_float(this._loc.progress, 1, [t]);
        this.queue_repaint();
    }
});

function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

/** The plan for the next wallpaper change: one effect for every monitor, from where the pointer is. */
export function makePlan(effect, pointer) {
    if (effect === 'none')
        return {effect: 'none', duration: 0};
    if (!EFFECTS.includes(effect)) {
        const bag = ['grow', 'grow', 'grow', 'grow', 'wipe', 'wipe', 'wipe', 'wave', 'wave', 'wave', 'fade'];
        effect = bag[Math.floor(Math.random() * bag.length)];
    }
    const angle = ANGLES[Math.floor(Math.random() * ANGLES.length)] * Math.PI / 180;
    return {effect, duration: effect === 'fade' ? 1.0 : 1.35, angle, pointer};
}

/**
 * Animate `actor` (the old background picture, above the new one) away with the plan's effect, then
 * destroy it. `monitor` is the monitor the picture covers. Returns the running timeline.
 */
export function animateOut(actor, monitor, plan, onDone) {
    const w = actor.width || monitor.width;
    const h = actor.height || monitor.height;
    const [px, py] = plan.pointer;
    const inside = px >= monitor.x && px < monitor.x + monitor.width &&
        py >= monitor.y && py < monitor.y + monitor.height;
    const origin = inside
        ? [(px - monitor.x) * w / monitor.width, (py - monitor.y) * h / monitor.height]
        : [w * (0.3 + 0.4 * Math.random()), h * (0.3 + 0.4 * Math.random())];
    const effect = new TransitionEffect();
    effect.setup({
        mode: MODES[plan.effect], origin, size: [w, h], angle: plan.angle,
        soft: (plan.effect === 'grow' ? 0.14 : 0.12) * Math.min(w, h),
    });
    actor.add_effect_with_name('wallrice-transition', effect);
    const timeline = new Clutter.Timeline({actor, duration: Math.round(plan.duration * 1000)});
    timeline.connect('new-frame', () => effect.setProgress(easeInOutCubic(timeline.get_progress())));
    timeline.connect('completed', () => {
        actor.destroy();
        onDone?.(timeline);
    });
    timeline.start();
    return timeline;
}
