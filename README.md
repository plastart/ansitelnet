# ansitelnet

A retro-faithful BBS terminal connector for Linux — single self-contained binary, no install
required. Dial into Telnet BBSs with full 16-colour ANSI art, upload and download files via
ZModem, browse a built-in server book and the live telnetbbsguide.com directory, and cap the
display width on wide monitors so 80-column art looks right.

```
ansitelnet bbs.example.net 23 -w 80
```

---

## Background

### What is a BBS?

A **Bulletin Board System** (BBS) is a computer server that users dial (or telnet) into to
exchange messages, play games, browse files, and transfer software. BBSs flourished from the
late 1970s through the 1990s, running on everything from Commodore 64s to dedicated PC towers,
and formed the backbone of pre-internet online culture in Europe and North America.

Modern BBSs keep the tradition alive over Telnet. Classics like **Mystic BBS**, **Synchronet**,
**Renegade**, and **PCBoard** still run today, serving sysops who hand-craft elaborate ANSI
welcome screens and door games.

### ANSI art and CP437

BBSs present their interfaces using **ANSI escape codes** combined with **IBM Code Page 437**
(CP437) — the original IBM PC character set that includes block-drawing characters (░▒▓█),
box-drawing lines (┌┐└┘│─), and a zoo of symbols that never made it into ASCII. The result is
pixel-art-like "ANSI art" that only looks right when the terminal speaks CP437 and renders the
IBM palette of 16 colours.

`ansitelnet` handles CP437→UTF-8 conversion transparently, sets the 16-colour ANSI palette via
OSC 4 terminal sequences, and forwards the raw ANSI escape codes to the local terminal so art
renders exactly as intended.

### ZModem

**ZModem** (1986, Chuck Forsberg) is the file-transfer protocol that replaced XModem and YModem
on BBSs. It is crash-recoverable, supports batch transfers, and negotiates binary (8-bit clean)
mode over Telnet. When a BBS initiates a ZModem transfer, it sends a trigger frame
(`**\x18B` — ZPAD ZPAD ZDLE ZHEX) that the terminal software must detect mid-stream and hand
off to `rz`/`sz` (part of **lrzsz**).

`ansitelnet` watches the byte stream for ZModem trigger frames, hands the socket to `rz` or
`sz`, and shows a live progress dialog. Binary mode (`IAC WILL BINARY` / `IAC DO BINARY`) is
negotiated at connection time so 8-bit data passes through unmangled.

---

## Features

| Feature | Details |
|---|---|
| **ANSI colour** | 8- or 16-colour mode; custom RGB palette via OSC 4 |
| **CP437 → UTF-8** | Block/box-drawing characters render correctly in any UTF-8 terminal |
| **ZModem download** | Auto-detected; live progress bar (filename, size, speed, ETA) |
| **ZModem upload** | Triggered from F12 menu; curses file picker; batch upload |
| **Server book** | Persistent local list of BBSs with name, host, port, colour mode |
| **BBS directory** | Live download from telnetbbsguide.com; filterable; add to server book |
| **Width cap** | `--width N` centres the display in N columns with `│` border lines |
| **Netcat mode** | `-n` skips Telnet IAC negotiation for raw TCP BBSs |

---

## Requirements

- Linux (or WSL on Windows)
- A terminal emulator with UTF-8 and 256-colour / true-colour support (Konsole, GNOME Terminal,
  iTerm2, Windows Terminal in WSL, …)
- For ZModem: `rz` and `sz` from the **lrzsz** package

```bash
# Debian / Ubuntu
sudo apt install lrzsz

# Arch
sudo pacman -S lrzsz
```

---

## Installation

### Pre-built binary (recommended)

Download `ansitelnet-linux-x86_64` from the [Releases](../../releases) page, make it
executable, and place it on your PATH:

```bash
chmod +x ansitelnet-linux-x86_64
mv ansitelnet-linux-x86_64 ~/.local/bin/ansitelnet
```

### Build from source

```bash
git clone https://github.com/yourname/ansitelnet
cd ansitelnet
make linux            # builds dist/ansitelnet
make install          # copies to ~/.local/bin/ansitelnet
```

`make linux` creates a Python virtualenv in `.buildenv/`, installs PyInstaller, and produces a
single self-contained binary in `dist/ansitelnet`. No system Python packages are modified.

---

## Usage

### Interactive server book (no arguments)

```
ansitelnet
```

Opens the curses-based server book. Keys:

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate list |
| `Enter` | Connect to selected BBS |
| `Ins` | Add new server |
| `F2` | Edit selected server |
| `Del` | Delete selected server |
| `F4` | Switch to BBS Directory tab |
| `F5` | Download / refresh BBS directory |
| `Tab` | Jump to search/filter field |
| `Esc` | Quit |

### Direct connection

```bash
ansitelnet <host> [port]          # Telnet, 16 colours
ansitelnet bbs.example.net 23
ansitelnet bbs.example.net 23 -8       # 8-colour ANSI mode
ansitelnet bbs.example.net 23 -n       # Netcat mode (no IAC)
ansitelnet bbs.example.net 23 -w 80    # cap display at 80 columns
```

### In-session keys

| Key | Action |
|---|---|
| `F12` | Open session menu (disconnect / upload) |

### Width cap (`-w N`)

For wide terminals, `-w 80` restricts the BBS content area to 80 columns and centres it with
`│` border lines. The BBS is told (via Telnet NAWS) that the terminal is N columns wide.
Resize the terminal freely — the borders redraw automatically.

```
ansitelnet bulletinboard.example.net -w 80
```

---

## Building for Windows

Windows builds are provided as release artifacts (see [Releases](../../releases)).

Native Windows terminal emulation (raw mode, `termios`, `SIGWINCH`) is not supported.
The binary will show the server book UI but will print a WSL install hint when you try to
connect. For full functionality, run ansitelnet inside
[WSL](https://learn.microsoft.com/en-us/windows/wsl/install).

### Via GitHub Actions (automatic)

Every tag push triggers `.github/workflows/build.yml` which builds `ansitelnet.exe` on a
Windows runner and attaches it to the release. Push a tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

### Via Wine (local cross-build)

```bash
sudo apt install wine

# Download Windows Python 3.x installer from python.org and install with Wine:
wine python-3.13.x-amd64.exe /quiet InstallAllUsers=0 PrependPath=1

# Install build dependencies:
wine pip install pyinstaller windows-curses

# Build:
make windows          # uses WINE_PY=wine python
```

The resulting `dist/ansitelnet.exe` is a native Windows PE binary.

---

## BBS Directory

`ansitelnet` can download a fresh list of active Telnet BBSs from
[telnetbbsguide.com](https://www.telnetbbsguide.com/) — no account required.

In the server book UI, press **F4** to open the **Verzeichnis** (Directory) tab, then **F5**
to download. The list is cached in `~/.config/ansitelnet/directory.json`.

From the directory tab:
- `Ins` — copy the selected BBS into your personal server book
- `Enter` — connect immediately

---

## Configuration

Settings are stored in `~/.config/ansitelnet/`:

| File | Contents |
|---|---|
| `servers.json` | Personal server book |
| `directory.json` | Cached BBS directory |

---

## Licence

MIT — see [LICENCE](LICENCE) for details.
