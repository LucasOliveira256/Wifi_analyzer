# 📡 WiFi Analyzer CLI

> A fast, feature-rich terminal WiFi analyzer for Linux — inspired by **gping** and **Ubiquiti's Wifiman**.  
> Real-time scanning, signal history graphs, channel congestion maps, and anti-interference suggestions — all from the command line.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Linux%20%2F%20Debian-orange?logo=linux)
![License](https://img.shields.io/badge/License-MIT-green)
![Dependencies](https://img.shields.io/badge/Dependencies-rich%20%7C%20nmcli-lightgrey)

---

## ✨ Features

### 📋 List Mode
- Displays all nearby access points with: **SSID**, **BSSID**, **Channel**, **Frequency (MHz)**, **Bandwidth**, **Band**, **Signal (dBm)**, **Quality**, **Congestion**, **Security**
- Navigable cursor with `↑ ↓` / `j k` keys
- Sort by signal strength, channel, SSID, or BSSID
- Filter by band: **2.4 GHz**, **5 GHz**, **6 GHz**, or **All**
- Color-coded signal quality (green → red)
- Per-channel congestion indicator with overlap detection (2.4 GHz non-overlapping channels: 1, 6, 11)

### 🗺️ Channel Map
- Visual histogram of channel usage for 2.4 GHz and 5 GHz
- Instant congestion visibility across all channels
- Toggle on/off with `m`

### 💡 Anti-Interference Suggestions
- Automatically recommends the least congested channel per band
- Updates live with every scan cycle

### 🔍 Focus Mode (Wifiman-style)
Press `Enter` or `f` on any network to enter **Focus Mode**:

- **Real-time signal graph** — gping-style thin line, no fill, spanning the full terminal width
- Signal history of up to **300 samples**
- Dense **dBm scale** on Y axis: −20 to −100 in 5 dBm increments
- Live statistics: **min / avg / max** dBm over the full history
- **Details panel**: SSID, BSSID, Band, Channel, Frequency, Width, Signal, Quality, Security
- **Interferers panel**: All other networks sharing the same channel, sorted by signal strength
- Navigate between networks with `↑ ↓` without leaving Focus Mode

### ⚡ Performance
- **Async rescanning**: background `nmcli rescan` every 4 seconds — UI never blocks
- **Instant cache reads** with `--rescan no` for sub-100ms refresh
- Default refresh rate: **1 second**
- Automatic fallback: `nmcli` → `iw scan dump` → `iw scan`

---

## 📸 Screenshots

```
 ██╗    ██╗██╗███████╗██╗      █████╗ ███╗   ██╗ █████╗ ██╗   ██╗███████╗███████╗██████╗
 ██║    ██║██║██╔════╝██║     ██╔══██╗████╗  ██║██╔══██╗██║   ██║╚══███╔╝██╔════╝██╔══██╗
 ██║ █╗ ██║██║█████╗  ██║     ███████║██╔██╗ ██║███████║██║   ██║  ███╔╝ █████╗  ██████╔╝
 ██║███╗██║██║██╔══╝  ██║     ██╔══██║██║╚██╗██║██╔══██║██║   ██║ ███╔╝  ██╔══╝  ██╔══██╗
 ╚███╔███╔╝██║██║     ███████╗██║  ██║██║ ╚████║██║  ██║╚██████╔╝███████╗███████╗██║  ██║
  ╚══╝╚══╝ ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚══════╝╚═╝  ╚═╝
```

| # | SSID         | BSSID             | CH  | MHz  | BW  | Band | Signal    | Quality          | Cong. | Sec.     |
|---|--------------|-------------------|-----|------|-----|------|-----------|------------------|-------|----------|
| ▶1 | MyNetwork   | F8:4E:33:F7:36:81 |  6  | 2437 | 20M | 2.4G | -53 dBm  | ▂▄▆█ Excellent  | ● 1   | WPA2     |
| 2 | Office_5G    | F8:4E:33:F7:36:85 | 36  | 5180 | 20M | 5G   | -67 dBm  | ▂▄▆  Great      | ● 1   | WPA2     |
| 3 | Neighbor     | C0:25:2F:97:15:AB | 10  | 2457 | 20M | 2.4G | -76 dBm  | ▂▄   Good       | ◑ 3   | WPA1 WPA2|

---

## 🔧 Requirements

| Requirement | Notes |
|---|---|
| **Python 3.10+** | f-strings with `match`, type union `X \| Y` |
| **python3-rich** | Terminal UI library |
| **nmcli** | NetworkManager CLI (pre-installed on most desktops) |
| **iw** *(optional)* | Fallback scanner if nmcli unavailable |
| **Root / sudo** | Required for scanning |

---

## 📦 Installation

```bash
# 1. Install system dependencies
sudo apt install python3-rich iw

# 2. Clone the repository
git clone https://github.com/yourusername/wifi-analyzer-cli.git
cd wifi-analyzer-cli

# 3. Run
sudo python3 wifi_analyzer.py          # Portuguese UI
sudo python3 wifi_analyzer_en.py       # English UI
```

> **No virtual environment needed** — only uses `rich` from the system package manager.

---

## 🚀 Usage

```bash
# Auto-detect interface
sudo python3 wifi_analyzer_en.py

# Specify interface
sudo python3 wifi_analyzer_en.py -i wlan0

# Faster refresh (0.5s) + filter 5 GHz only
sudo python3 wifi_analyzer_en.py -i wlan0 --refresh 0.5 --filter 5G

# Sort by channel instead of signal
sudo python3 wifi_analyzer_en.py --sort channel

# Debug: show raw nmcli output and exit (no root needed)
python3 wifi_analyzer_en.py --debug -i wlan0
```

### CLI Options

| Option | Default | Description |
|---|---|---|
| `-i`, `--iface` | auto-detect | Wireless interface name (e.g. `wlan0`, `wlo1`) |
| `-r`, `--refresh` | `1.0` | UI refresh interval in seconds |
| `-f`, `--filter` | `ALL` | Band filter: `ALL`, `2.4G`, `5G`, `6G` |
| `--sort` | `signal` | Sort column: `signal`, `channel`, `ssid`, `bssid` |
| `--debug` | off | Print raw nmcli output and exit |

---

## ⌨️ Keyboard Shortcuts

### List Mode

| Key | Action |
|---|---|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `Enter` / `f` | Focus selected network |
| `s` | Sort by signal |
| `c` | Sort by channel |
| `n` | Sort by SSID |
| `2` | Filter 2.4 GHz |
| `5` | Filter 5 GHz |
| `a` | Show all bands |
| `m` | Toggle channel map |
| `q` | Quit |

### Focus Mode

| Key | Action |
|---|---|
| `Esc` / `b` | Back to list |
| `↑` / `k` | Previous network |
| `↓` / `j` | Next network |
| `q` | Quit |

---

## 🏗️ Architecture

```
wifi_analyzer_en.py
│
├── Scanner layer
│   ├── scan_nmcli()       — primary: reads NM cache instantly
│   ├── _trigger_rescan()  — async background rescan via nmcli
│   ├── scan_iw()          — fallback: iw scan dump / iw scan
│   └── scan_auto()        — auto-selects available backend
│
├── History layer
│   └── signal_history{}   — per-BSSID deque of 300 samples
│
├── UI layer (Rich)
│   ├── List Mode
│   │   ├── build_table()        — main network table with cursor
│   │   ├── build_channel_map()  — 2.4/5 GHz histogram
│   │   └── build_suggestions()  — anti-interference tips
│   │
│   └── Focus Mode
│       ├── build_signal_graph() — real-time gping-style graph
│       ├── build_focus_details()— network info panel
│       └── build_focus_peers()  — interferers on same channel
│
└── Input layer
    └── read_key_nonblock()  — non-blocking terminal input
```

---

## 📡 Signal Quality Reference

| dBm Range | Quality | Typical Use Case |
|---|---|---|
| −20 to −50 | 🟢 **Excellent** | Video calls, fast transfers |
| −50 to −65 | 🟢 **Great** | HD streaming, VoIP |
| −65 to −75 | 🟡 **Good** | Web browsing, email |
| −75 to −85 | 🟠 **Weak** | Basic connectivity |
| −85 to −100 | 🔴 **Very Weak** | Unreliable connection |

---

## 🛠️ Troubleshooting

**No networks showing:**
```bash
# Check your interface name
ip a

# Run debug to see raw nmcli output
python3 wifi_analyzer_en.py --debug -i wlan0

# Force a rescan via NetworkManager
nmcli device wifi rescan ifname wlan0
```

**Interface not found:**
```bash
# List wireless interfaces detected by NM
nmcli device | grep wifi
```

**Permission denied:**
```bash
# Always run with sudo
sudo python3 wifi_analyzer_en.py
```

**`iw` not found (fallback only):**
```bash
sudo apt install iw
```

---

## 🤝 Contributing

Pull requests welcome! Some ideas for contributions:

- [ ] OUI vendor lookup (manufacturer from BSSID)
- [ ] Export scan results to JSON / CSV
- [ ] 6 GHz channel map support
- [ ] GPS tagging for AP location tracking
- [ ] Configurable alert thresholds (signal drop notifications)
- [ ] Mouse click support for network selection

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Acknowledgements

- [**gping**](https://github.com/orf/gping) — inspiration for the real-time graph style
- [**Ubiquiti Wifiman**](https://wifiman.com/) — inspiration for the Focus Mode layout
- [**Rich**](https://github.com/Textualize/rich) — the excellent terminal UI library that powers the interface
