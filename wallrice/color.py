"""Colour maths: hex <-> rgb (0..1 floats), WCAG luminance and contrast, mixing."""
import colorsys

BLACK, WHITE = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)


def hex2rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb2hex(c):
    return "#" + "".join(f"{round(max(0.0, min(1.0, x)) * 255):02x}" for x in c)


def rgb255(c):
    return tuple(round(max(0.0, min(1.0, x)) * 255) for x in c)


def luminance(c):
    def lin(x):
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def hls(c):
    return colorsys.rgb_to_hls(*c)


def from_hls(h, l, s):
    return colorsys.hls_to_rgb(h, l, s)


def toward(c, target, other, ratio, step=0.04):
    """Move colour c toward `target` until its contrast against `other` reaches `ratio`."""
    orig, t = c, 0.0
    while contrast(c, other) < ratio and t < 1:
        t = min(1.0, t + step)
        c = mix(orig, target, t)
    return c


def hue_distance(a, b):
    """Distance between two hues on the 0..1 colour wheel (0..0.5)."""
    d = abs(a - b) % 1.0
    return min(d, 1 - d)
