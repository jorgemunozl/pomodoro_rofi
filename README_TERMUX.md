# 🍅 Pomodoro on Termux (Android phone)

Setup and usage guide for running the pomodoro timer on a phone via
[Termux](https://termux.com). Everything below was verified on a real
device (aarch64, Android 12/13) over SSH.

---

## What works on the phone

| Area | Status |
|---|---|
| Timer engine (work/break/reflect cycles, pause, skip, stop) | ✅ |
| Startup presets (`startup`, `morning`, `noon`, `afternoon`, …) | ✅ |
| ARC music playback (shuffled playlist + silence tracks, volume fade) | ✅ via `mpv` |
| Time announcements via `gtts-cli` | ✅ (needs internet) |
| Notifications | ✅ fallback: `dunstify` → `termux-notification` → printed line |
| `pomodoro_phone` CLI menu | ✅ (needs `termux-api`) |
| Rofi menu UI (`./pomodoro` with no args) | ❌ rofi is desktop-only |
| Fullscreen study **videos** | ❌ audio-only playback on the phone |
| i3 workspace switching, obsidian/firefox commands | ❌ no-ops (no i3 on Android) |

---

## 1. Install dependencies

```bash
pkg update && pkg install -y python mpv socat ffmpeg openssh termux-api

# Time announcements ("The time is …") — needs internet at runtime
python3 -m pip install gTTS
```

- `mpv` — audio playback (ARC music, bells, announcements)
- `socat` — mpv IPC (volume fade, pause)
- `ffmpeg` — generates the silence tracks between ARC songs
- `openssh` — `scp`/`ssh` to copy media from your laptop (client)
- `termux-api` — `termux-notification` / `termux-media-player` used by `pomodoro_phone`

## 2. Get the code

```bash
git clone https://github.com/jorgemunozl/pomodoro_rofi.git
cd pomodoro_rofi
git config user.name  "you"          # needed for commits
git config user.email "you@mail.com"
```

## 3. Copy the media from your laptop (one-time)

The phone and laptop must be on the same WiFi. First add the phone's
public key to the laptop so `scp` doesn't ask for a password:

```bash
# on the phone: show the key, then add it on the laptop
cat ~/.ssh/id_ed25519.pub
# on the laptop:  echo '<the key>' >> ~/.ssh/authorized_keys
```

Then, from the phone (replace `jorge@192.168.18.14` with your laptop):

```bash
mkdir -p ~/Videos/study

# sound effects (bells, finish, push-ups) — tiny, required
scp -r jorge@192.168.18.14:~/Videos/study/sound_effects/ ~/Videos/study/

# ARC music directories
scp -r jorge@192.168.18.14:~/Videos/current-arc/ ~/Videos/
scp -r jorge@192.168.18.14:~/Videos/past-arc/    ~/Videos/
scp -r jorge@192.168.18.14:~/Videos/music/       ~/Videos/

# optional — audio-only tracks of the study videos (≈2.4 GB)
scp -r "jorge@192.168.18.14:~/Videos/study/*.mp3" ~/Videos/study/
```

| Path | Contents | Size (laptop) |
|---|---|---|
| `~/Videos/study/sound_effects/` | bells, finish, push-ups | few MB |
| `~/Videos/current-arc/` | current soundtrack | ~86 MB |
| `~/Videos/past-arc/` | older soundtrack | ~52 MB |
| `~/Videos/music/` | extra music | ~895 MB |
| `~/Videos/study/*.mp3` | audio-only videos | ~2.4 GB |
| `~/Videos/study/*.mp4|webm` | full videos (audio-only on phone) | ~14 GB |

---

## 4. Run it

```bash
cd ~/pomodoro_rofi

./pomodoro status                 # current timer state ("" = idle)
./pomodoro stop | next | toggle   # control an active session
./pomodoro <preset>               # start a preset (live countdown, Ctrl+C stops)
./pomodoro start -t <task> -v <dir-or-file> [-r 25-5] [-c N] [-a]
./pomodoro_phone                  # CLI menu (Termux style)
```

Available presets and their music:

| Preset | Music source | Description |
|---|---|---|
| `startup` | current-arc | 15m polymath → 2m set-up → 13m apps → 3× 25/5 |
| `startup2` | current-arc → music | same, switches to `music/` |
| `startup3` | current-arc → past-arc → music | longest chain |
| `morning` | current-arc | morning ritual (plan, chess, stretch) |
| `noon` | past-arc | post-lunch: polymath, apps, github |
| `afternoon` | past-arc | 2× 29m problem solving |
| `night_hardcore` / `night_light` | current-arc / study video | evening routines |
| `cleaning` | current-arc | 25m cleaning |
| `test` | — | 12-second phases, quick sanity check |

## 5. Differences from the desktop

- **No `/tmp` on Termux** — state files, pid files, and the mpv socket
  live in `$TMPDIR` (`tempfile.gettempdir()`, i.e.
  `/data/data/com.termux/files/usr/tmp`). The desktop still uses `/tmp`.
- **Notifications** fall back in order: `dunstify` (desktop) →
  `termux-notification` (needs `termux-api`) → plain printed line.
- **gtts announcements** need internet (Google TTS). Fired on session
  start and after every pomodoro. Disable with
  `ANNOUNCE_TIME_ON_DONE = False` in `pomodoro_lib/config.py`.
- **mpv runs `--no-video`** — ARC music, bells, and announcements play;
  study *videos* won't display (audio-only).
- **i3/obsidian/firefox commands** are no-ops on the phone.
- **rofi menu** is desktop-only — use presets, `start`, or
  `pomodoro_phone` instead.

## 6. Keeping in sync with the laptop

```bash
# phone pulls the laptop's version:
git remote add laptop ssh://jorge@192.168.18.14/home/jorge/project/pomodoro_rofi
git pull laptop master

# laptop pulls the phone's version (phone's sshd port, e.g. 8022):
#   git remote add phone ssh://u0_a247@192.168.18.185:8022/data/data/com.termux/files/home/pomodoro_rofi
#   git pull phone master
```

## Troubleshooting

- **`pomodoro status` says nothing** → no active session (normal).
- **"A session is already active"** after a crash → `./pomodoro stop`.
- **No music in ARC presets** → check `~/Videos/current-arc|past-arc`
  exist and contain mp3s; first run generates silence tracks with
  ffmpeg in `$TMPDIR`.
- **No announcements** → `gtts-cli` missing (`pip install gTTS`) or
  no internet.
- **No notifications** → install `termux-api`; otherwise the timer
  prints them to the terminal instead.
