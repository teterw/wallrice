"""derive(): a wallpaper's 16 colours -> the colours the desktop uses, readable on any wallpaper.

Background always dark (relative luminance <= 0.03), text >= 7:1 against it (WCAG AAA), accent
>= 3:1 (UI components), muted text and terminal colours >= 4.5:1 (AA)."""
from .color import BLACK, WHITE, contrast, from_hls, hex2rgb, hls, hue_distance, luminance, mix, rgb2hex, toward

BRAND = hex2rgb("#8b5cf6")  # violet: grey wallpapers have no hue of their own to give
KEYS = ("bg", "fg", "accent", "on_accent", "surface", "surface2", "muted")


# Terminal colour slots 1-6 (and 9-14): red, yellow, green, cyan, blue, magenta hues
ANSI_HUES = {1: 0.0, 2: 0.33, 3: 0.14, 4: 0.6, 5: 0.83, 6: 0.5}


def ansi_tint(i, accent):
    """A readable ANSI-like colour for terminal slot i, harmonised with the accent: grey wallpapers
    would otherwise give terminals with no colours to tell errors from successes."""
    c = from_hls(ANSI_HUES[i % 8], 0.62 if i < 8 else 0.72, 0.5)
    return mix(c, accent, 0.25)


def accent_score(c):
    """Saturated, mid-light colours make good accents."""
    _, l, s = hls(c)
    return s * (1 - abs(l - 0.55))


def derive(palette, brand=BRAND):
    bg = hex2rgb(palette["background"])
    if luminance(bg) > 0.03:
        bg = mix(bg, BLACK, 0.6)
    while luminance(bg) > 0.03:
        bg = mix(bg, BLACK, 0.2)
    fg = toward(hex2rgb(palette["foreground"]), WHITE, bg, 7.0)

    candidates = [palette.get(f"color{i}") for i in (*range(1, 7), *range(9, 15))]
    candidates = [hex2rgb(c) for c in candidates if c]
    accent = max(candidates, key=accent_score) if candidates else brand
    h, l, s = hls(accent)
    if s < 0.08:    # grey wallpaper: no hue to keep (it would come out red), use the brand colour
        accent = brand
    elif s < 0.25:  # low-colour wallpaper: give the accent some life without changing its hue
        accent = from_hls(h, max(l, 0.55), 0.45)
    accent = toward(accent, WHITE, bg, 3.0)
    on_accent = BLACK if contrast(accent, BLACK) >= contrast(accent, WHITE) else WHITE
    term = []
    for i in range(16):
        c = hex2rgb(palette.get(f"color{i}", "#808080"))
        if i % 8 in ANSI_HUES and hls(c)[2] < 0.12:
            c = ansi_tint(i, accent)  # a grey slot: a real colour, tinted toward the accent
        if i not in (0, 8):
            c = toward(c, WHITE, bg, 4.5)  # every terminal colour readable on the background
        term.append(c)
    return {"bg": bg, "fg": fg, "accent": accent, "on_accent": on_accent,
            "surface": mix(bg, fg, 0.07), "surface2": mix(bg, fg, 0.14),
            "muted": toward(mix(fg, bg, 0.45), WHITE, bg, 4.5), "term": term}


def hexes(theme):
    """{key: "#rrggbb"} for the named colours (not the terminal list)."""
    return {k: rgb2hex(theme[k]) for k in KEYS}


def mix_theme(a, b, t):
    """Colours partway between two themes, for smooth recolouring in the picker."""
    out = {k: mix(a[k], b[k], t) for k in KEYS}
    out["term"] = [mix(x, y, t) for x, y in zip(a["term"], b["term"])]
    return out


def nearest(accent, named):
    """The named colour ({name: "#hex"}) closest to the accent. Hue decides (named palettes such as
    GNOME's differ mostly in hue, and a darker "purple" is still the right match for violet); near-grey
    accents go to the greyest name."""
    h1, l1, s1 = hls(accent)
    if s1 < 0.15:
        return min(sorted(named), key=lambda n: (hls(hex2rgb(named[n]))[2], abs(hls(hex2rgb(named[n]))[1] - l1)))

    def dist(name):
        h2, l2, s2 = hls(hex2rgb(named[name]))
        return hue_distance(h1, h2) * 6 + abs(l1 - l2) * 0.5 + abs(s1 - s2) * 0.3 + (1 if s2 < 0.2 else 0)
    return min(sorted(named), key=dist)
