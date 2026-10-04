# Changelog

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
