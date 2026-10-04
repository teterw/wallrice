# Changelog

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
