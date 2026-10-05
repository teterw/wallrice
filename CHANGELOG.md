# Changelog

## v0.7.0: every part on or off

- `wallrice off PART…` / `wallrice on PART…` / `wallrice off all` / `wallrice on all`, and
  `wallrice parts` to see them: apps, icons, terminal, dock, taskbar-icons, topbar, transitions and
  rotation. Each choice is saved and respected by every later wallpaper change; the wallpaper itself
  always changes.
- Off puts that part's originals back from the backup at once (GTK theme, accent, gtk.css, icon
  theme, terminal palette, dock colours) and forgets them there; on themes it from the current
  wallpaper at once.
- GNOME, live: `topbar` off gives GNOME's own top bar back, `taskbar-icons` off gives the dock and
  the top bar's launchers their colourful icons, `dock` off drops the dock's theme colours.
- The picker's desktop mock draws what's on (stock bar, colourful dock icons).
- The older commands are shortcuts onto the parts: `terminal on|off`, `animations on|off`,
  `bar mono|colour`, `rotate off|MINUTES` (rotate off now remembers the interval for `on`).

## v0.6.0: terminal colours on or off

- `wallrice terminal on|off` (no argument shows which): whether terminals take the wallpaper's colours.
  The choice is saved, so every later wallpaper change (picker, timer, random) respects it; the rest of
  the desktop keeps following the wallpaper either way.
- `off` puts the terminal's own settings back from the backup (Ptyxis's original palette,
  xfce4-terminal's colours) and resets open terminals to their own colours; `on` recolours terminals
  from the current wallpaper at once, without re-theming the rest.
- The Ptyxis palette has its own A/B copy, so switching back on mid-session still updates open windows.

## v0.5.1: polish

- `wallrice walls import FILE`: take Keep/Remove choices from another review.json, such as Chiron
  Stick's `walls-review.json`. Choices already made here win; removed pictures leave the disk.
- GNOME: the extension skips the Shell's window animations for the picker, so its own zoom hands over
  to the desktop seamlessly.
- Colours: text is near-white with only a tint of the picture (a saturated foreground no longer gives
  neon text), and a dark accent is lightened in its own colour instead of being greyed by white.

## v0.5.0: every common desktop

- Backends for KDE Plasma, Xfce, Cinnamon, MATE, LXQt, wlroots compositors (Hyprland, Sway, river, …)
  and X11 window managers (i3, bspwm, Openbox, …), each chosen by detection. See the README's table
  for what each does live.
- X11 desktops get animated changes again: the desktop-layer overlay from the stick (grow from the
  pointer, wipe, wave, fade), with the real wallpaper switched underneath; timer jobs wait for it.
- wlroots: swww's own transitions (growing from the pointer on Hyprland), border colours live and as
  include files, waybar reloaded.
- KDE: A/B colour schemes (Plasma won't re-apply the current one) with the wallpaper's accent.
- Backups and uninstall cover xfconf and KDE settings too.
- `tools/desktop-test.sh xfce|sway|kde`: runs a desktop headless in a throwaway container and saves
  screenshots of the themed desktop, the transitions, the picker and the review.
- doctor: clearer Super+W lines for desktops where it's set by hand; cursor-only themes no longer
  count as icon themes missing a cache.

## v0.4.0: the GNOME Shell extension

- Animated wallpaper changes in GNOME Shell (45-50): a GLSL effect on the old picture reveals the new
  one with a soft circle growing from the pointer, an angled soft wipe, a rippling wave, or a fade
  (1.35 s, eased), on every monitor. wallrice calls `Prepare(effect)` over D-Bus just before setting
  the wallpaper; the picker asks for none, since it already animated the change. Changes wallrice
  didn't make keep the Shell's own fade.
- The islands top bar: workspaces 1-4 (click or scroll), launchers (first three favourites with
  symbolic icons, and the picker), the focused window's title in the centre, cpu/mem/net (Vitals' if
  installed), system indicators, the clock moved right, a notification bell. Turning the extension
  off restores the stock bar.
- Nine bar styles (outlined, side bars, glow, pills, underline, glass, tinted, floating bar, filled
  clock), chosen with `wallrice bar`: a chooser that previews each on the current wallpaper and
  restyles the real top bar live; Enter keeps, Esc reverts. `wallrice bar STYLE` for scripts. The
  picker's desktop mock draws the chosen style.
- Dash to Dock / Ubuntu Dock: floating, rounded, in the theme's colours, with monochrome icons (the
  running dots keep the accent); `wallrice bar colour` turns colour icons back on.
- The stylesheet and settings live in `~/.local/share/wallrice/gnome-shell.{css,json}`; the extension
  reloads them as soon as they change.
- `tools/shell-test.sh`: runs the extension in a private headless GNOME Shell (own home, dconf and
  session bus) and takes screenshots of the bar styles and transitions.

## v0.3.0: the picker

- `wallrice pick` (Super+W, *Wallpapers* in the app menu): a full-screen preview screen. It opens by
  shrinking the current wallpaper, drawn exactly as the desktop shows it, into a card with the
  screen's shape, over a blurred, darkened backdrop; the UI slides in.
- Filmstrip with spring scrolling, the selected picture raised with an accent glow; the card
  cross-fades and sharpens; a live mock of the themed desktop at real size and the palette with hex
  codes; everything recolours smoothly (0.45 s). Type to search, Tab for the bare picture.
- Enter grows the picture to full screen while the theme is applied, and closes only once the desktop
  shows it (GNOME's own fade included). Esc goes back the same way.
- Delete / ✕ removes a wallpaper like a review Remove; Ctrl+Z restores the exact previous choice; a
  held Delete acts once; removing the current wallpaper makes Esc apply the one on show.
- One background loader by priority, LRU caches, reduced-size JPEG decoding: no stutter.
- Terminal colours: grey slots become ANSI-like colours tinted toward the accent, so grey wallpapers
  still give terminals where errors and successes look different.

## v0.2.0: the Yes/No review

- `wallrice walls review`: every picture not reviewed yet, whole, on a blurred copy of itself, with
  collection, title, size and credit. Keep / Remove buttons and keys, undo, progress, and animations:
  kept cards fly up and to the right, removed ones drop away with a red tint, the next scales in.
- Every choice is saved at once; the review resumes where it stopped. Removed pictures leave the disk
  when it ends (sparse-checkout exclusions for git collections, so updates never bring them back).
  If the current wallpaper was removed, another one is applied.
- Key auto-repeat never makes a choice: a press of a key that's still down is ignored, and choices
  are at least 0.2 s apart.
- `walls update --background` downloads detached, with a log.

## v0.1.0: the theme engine and GNOME

- `derive()`: contrast-safe colours from any wallpaper (a dark background, text at 7:1, accent at 3:1,
  muted text and terminal colours at 4.5:1); violet for grey wallpapers.
- Palettes from wallust when installed, otherwise a built-in Pillow extractor; cached per image.
- Desktop detection (desktop, session, compositor, distro, package manager, tools).
- Renderers: GTK 3 A/B theme on adw-gtk3-dark, GTK 4 / libadwaita CSS variables, terminal escape
  sequences, Ptyxis A/B palette, kitty, alacritty, foot, wezterm, Konsole, btop, rofi, wofi, fuzzel,
  waybar, and a Papirus folder-colour overlay.
- GNOME backend: wallpaper, GTK theme, nearest named accent, icons, Ptyxis, Dash to Dock, in one dconf
  transaction each; Super+W and Shift+Super+W.
- Never half-themed: everything is rendered in memory and written only if all of it succeeded.
- Backups of every setting and file before the first change; `uninstall.sh` restores them.
- `wallrice doctor`, `install.sh` and `uninstall.sh` (per user, `--dry-run`), rotation timer.
- Wallpaper collections (`walls update`, `walls status`): sparse git clones and a SHA-256-pinned list
  of ESA/Webb and ESA/Hubble images.
