# wallrice design

wallrice makes the whole desktop take its colours from the wallpaper, with a full-screen picker
that previews the theme before applying it, animated wallpaper changes, and curated wallpaper
collections with a Yes/No review. It is the portable successor of the Chiron Stick rice
(https://github.com/teterw/chiron-stick, `rice/`, MIT).

## Decisions (2026-10-04)

| Question | Decision |
|---|---|
| Name, visibility | `wallrice`, public, MIT |
| Desktops | GNOME first (Fedora 44, GNOME 50, Wayland); KDE, Xfce, wlroots and X11 WMs after, each VM-tested |
| Accent for grey wallpapers | violet `#8b5cf6` |
| GNOME Shell side | companion extension `wallrice@teterw.github.io`: shader transitions + islands top bar |
| Picker / review toolkit | GTK 3 + cairo (CPU drawing; X11 and Wayland); rofi/wofi/fuzzel or fzf+chafa fallbacks |
| Palette | wallust when installed, else a built-in Pillow extractor (wallust isn't packaged on Fedora) |

## Shape

```
collections.conf ─► walls update ─► ~/Pictures/walls/<collection>/   (sparse git clones, pinned lists)
walls review ─► review.json (keep/drop)        picker (Super+W) ─► apply(image)
apply: palette ─► derive() contrast-safe theme ─► render every output in memory ─► write all ─► activate
                                         │
               backend chosen by detection (desktop, session, compositor, installed tools)
               set wallpaper · live colours · terminal colours · icons · transition · Super+W
```

- `wallrice/color.py`, `theme.py`: contrast maths and `derive()` (WCAG: text ≥ 7:1, accent ≥ 3:1,
  muted and terminal colours ≥ 4.5:1, background always dark).
- `wallrice/palette.py`: 16 colours per image (wallust or Pillow), cached by `sha1(path|size|mtime)`.
- `wallrice/render/`: pure functions, theme → `{path: text}`. Only for apps that are present.
- `wallrice/backends/`: one module per desktop with the same interface (`set_wallpaper`,
  `outputs`, `activate`, `bind_key`, `transition`, backups).
- `wallrice/engine.py`: `apply()`. Everything is rendered in memory first; nothing is written
  unless all of it rendered, so the desktop is never half-themed. Live activation steps are
  best-effort: each one that can't run prints one line and the rest go on.
- Live GTK3 recolouring uses two generated themes, `Wallrice-a` and `Wallrice-b`: write the one not
  in use, then switch to it. The same A/B slot is used for the Papirus folder overlay and the Ptyxis
  palette, so every running app sees a real change.

## GNOME specifics

- Wallpaper: `org.gnome.desktop.background picture-uri` and `picture-uri-dark`, `picture-options zoom`.
- GTK3 apps: A/B theme (adw-gtk3-dark plus `@define-color` overrides), live.
- GTK4/libadwaita apps: `~/.config/gtk-4.0/gtk.css` (CSS variables and `@define-color`), read when an
  app starts. The Shell and running libadwaita apps get the nearest named `accent-color` live.
- Terminals: OSC 4/10/11/12 to every pty the user owns (running windows), plus an A/B Ptyxis palette.
- Dock: Dash to Dock background and running-dot colours.
- Extension: replaces the Shell's 1 s cross-fade (`BackgroundManager._swapBackgroundActor`) with
  grow/wipe/wave/fade shaders, and restyles the top bar as accent-bordered islands from a generated
  stylesheet it reloads live.

## Releases

v0.1 engine + GNOME backend + doctor + install/uninstall + tests/CI · v0.2 collections + review ·
v0.3 picker · v0.4 GNOME extension · v0.5+ other desktops.
