#!/usr/bin/env python3
"""
wifi_analyzer.py — WiFi Analyzer for network auditing and management
gping + Wifiman style: fast refresh, rich terminal UI, real-time signal graph.

Dependências:
    sudo apt install python3-rich iw

Uso:
    sudo python3 wifi_analyzer.py
    sudo python3 wifi_analyzer.py -i wlo1
    sudo python3 wifi_analyzer.py -i wlo1 --refresh 1.5 --filter 5G
    python3 wifi_analyzer_en.py --debug -i wlo1
"""

import subprocess, re, sys, time, argparse, shutil, os
from collections import defaultdict, deque
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich.columns import Columns
    from rich import box
    from rich.align import Align
except ImportError:
    print("Dependência ausente. Instale com:\n  sudo apt install python3-rich")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────────────────────

BANNER_WIFI = [
    '██╗    ██╗██╗███████╗██╗',
    '██║    ██║██║██╔════╝██║',
    '██║ █╗ ██║██║█████╗  ██║',
    '██║███╗██║██║██╔══╝  ██║',
    '╚███╔███╔╝██║██║     ██║',
    ' ╚══╝╚══╝ ╚═╝╚═╝     ╚═╝',
]

BANNER_ANALYZER = [
    ' █████╗ ███╗   ██╗ █████╗ ██╗  ██╗   ██╗███████╗███████╗██████╗ ',
    '██╔══██╗████╗  ██║██╔══██╗██║  ╚██╗ ██╔╝╚══███╔╝██╔════╝██╔══██╗',
    '███████║██╔██╗ ██║███████║██║   ╚████╔╝   ███╔╝ █████╗  ██████╔╝',
    '██╔══██║██║╚██╗██║██╔══██║██║    ╚██╔╝   ███╔╝  ██╔══╝  ██╔══██╗',
    '██║  ██║██║ ╚████║██║  ██║███████╗██║   ███████╗███████╗██║  ██║',
    '╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝   ╚══════╝╚══════╝╚═╝  ╚═╝',
]

def build_header_text() -> Text:
    t = Text(justify="center")
    t.append("\n")
    for i, (w_line, a_line) in enumerate(zip(BANNER_WIFI, BANNER_ANALYZER)):
        t.append(w_line, style="bold bright_cyan")
        t.append("  ")
        t.append(a_line, style="bold cyan")
        t.append("\n")
    t.append("WiFi Analyzer  ·  Auditing  ·  Channel Management  ·  Anti-Interference\n",
              style="dim")
    return t

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────

GRAPH_WIDTH  = 300
GRAPH_HEIGHT = 28
SIGNAL_MIN   = -100
SIGNAL_MAX   = -20

BAND_COLORS = {
    "2.4G": "bold green",
    "5G":   "bold cyan",
    "6G":   "bold magenta",
    "?":    "dim white",
}

SIGNAL_BARS = [
    (-50,  "[bold green]▂▄▆█[/bold green]  Excellent"),
    (-65,  "[bold green]▂▄▆[/bold green][dim]█[/dim]  Great    "),
    (-75,  "[yellow]▂▄[/yellow][dim]▆█[/dim]  Good     "),
    (-85,  "[orange3]▂[/orange3][dim]▄▆█[/dim]  Weak     "),
    (-999, "[red]▂[/red][dim]▄▆█[/dim]  Very weak"),
]

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def channel_to_band(ch: int, freq_mhz: int = 0) -> str:
    if freq_mhz >= 5945: return "6G"
    if freq_mhz >= 5000 or ch > 14: return "5G"
    if 1 <= ch <= 14: return "2.4G"
    return "?"

def signal_bar(dbm: int) -> str:
    for threshold, bar in SIGNAL_BARS:
        if dbm >= threshold:
            return bar
    return SIGNAL_BARS[-1][1]

def signal_color(dbm: int) -> str:
    if dbm >= -50: return "bold green"
    if dbm >= -65: return "green"
    if dbm >= -75: return "yellow"
    if dbm >= -85: return "orange3"
    return "red"

def channel_congestion(networks: list, target_ch: int, band: str) -> int:
    overlap = {1:[1,2,3,4,5], 6:[4,5,6,7,8], 11:[9,10,11,12,13]}
    overlapping = set()
    for anchor, channels in overlap.items():
        if target_ch in channels:
            overlapping.update(channels)
    if not overlapping:
        overlapping = {target_ch}
    return sum(1 for n in networks if n.get("band") == band and n.get("channel") in overlapping)

def suggest_channel(networks: list, band: str) -> str:
    candidates = [1,6,11] if band == "2.4G" else ([36,40,44,48,149,153,157,161] if band == "5G" else [])
    if not candidates: return "—"
    usage = {ch: sum(1 for n in networks if n.get("band") == band and n.get("channel") == ch)
             for ch in candidates}
    best = min(usage, key=usage.get)
    return f"CH {best} ({usage[best]} network{'s' if usage[best]!=1 else ''})"

# ──────────────────────────────────────────────────────────────
# Scanner — nmcli (primário) + iw (fallback)
# ──────────────────────────────────────────────────────────────

def get_interfaces() -> list:
    try:
        out = subprocess.check_output(["nmcli","-t","-f","DEVICE,TYPE","device"],
                                      text=True, stderr=subprocess.DEVNULL)
        ifaces = [l.split(":")[0] for l in out.splitlines() if ":wifi" in l]
        if ifaces: return ifaces
    except Exception: pass
    try:
        out = subprocess.check_output(["iw","dev"], text=True, stderr=subprocess.DEVNULL)
        return re.findall(r"Interface\s+(\S+)", out)
    except Exception:
        return []

def _parse_nmcli_output(out: str) -> list:
    """Parseia a saída do nmcli -t e retorna list de networks."""
    networks = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # nmcli escapa ':' no BSSID com backslash: F8\:4E\: ...
        # split(":") gera octetos com \ no final: "F8\", "4E\", ..., "81"
        parts = line.split(":")
        bssid_parts = []
        rest_start  = 0
        for i, p in enumerate(parts):
            clean = p.rstrip("\\").strip()
            if len(clean) == 2 and all(c in "0123456789ABCDEFabcdef" for c in clean):
                bssid_parts.append(clean)
                if len(bssid_parts) == 6:
                    rest_start = i + 1
                    break
            else:
                break
        if len(bssid_parts) != 6:
            continue
        bssid  = ":".join(bssid_parts).upper()
        fields = parts[rest_start:]
        if len(fields) < 7:
            continue
        ssid     = fields[0].strip() or "<hidden>"
        chan_str = fields[2].strip()
        freq_str = fields[3].strip()
        sig_str  = fields[5].strip()
        security = " ".join(fields[7:]).strip() if len(fields) > 7 else ""
        try:    ch = int(chan_str)
        except: ch = 0
        fm = re.search(r"(\d{4,5})", freq_str)
        freq_mhz = int(fm.group(1)) if fm else 0
        try:    sig_dbm = (int(sig_str) // 2) - 100
        except: sig_dbm = -100
        networks.append({
            "bssid": bssid, "ssid": ssid,
            "channel": ch, "freq_mhz": freq_mhz, "freq": freq_mhz,
            "signal": sig_dbm, "width": 20,
            "band": channel_to_band(ch, freq_mhz),
            "security": set(),
            "security_str": security or "Open",
        })
    return networks


# Processo de rescan em background — dispara nmcli rescan sem bloquear a UI
_rescan_proc: subprocess.Popen | None = None
_rescan_iface: str = ""
_last_rescan: float = 0.0
RESCAN_INTERVAL = 4.0   # segundos entre rescans (nmcli leva ~3s)

def _trigger_rescan(iface: str):
    """Triggers an async rescan via NetworkManager."""
    global _rescan_proc, _rescan_iface, _last_rescan
    now = time.time()
    # Só dispara se o anterior já terminou e passou o intervalo minimo
    if _rescan_proc is not None:
        if _rescan_proc.poll() is None:
            return   # ainda rodando
        _rescan_proc = None
    if now - _last_rescan < RESCAN_INTERVAL:
        return
    try:
        _rescan_proc  = subprocess.Popen(
            ["nmcli", "device", "wifi", "rescan", "ifname", iface],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _rescan_iface = iface
        _last_rescan  = now
    except FileNotFoundError:
        pass


def scan_nmcli(iface: str) -> list:
    """
    Reads NM cache immediately (--rescan no) for instant response,
    while triggering an async background rescan to keep data fresh.
    """
    # Dispara rescan em background sem bloquear
    _trigger_rescan(iface)

    # Lê o cache atual — retorno imediato
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "BSSID,SSID,MODE,CHAN,FREQ,RATE,SIGNAL,BARS,SECURITY",
             "device", "wifi", "list", "ifname", iface, "--rescan", "no"],
            text=True, stderr=subprocess.PIPE, timeout=10)
        if out.strip():
            return _parse_nmcli_output(out)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass
    return []

def _finalize(current: dict, networks: list):
    freq = current.get("freq", 0)
    ch   = current.get("channel")
    if ch is None and freq:
        if 2412 <= freq <= 2484:   ch = (freq-2407)//5 if freq != 2484 else 14
        elif 5000 <= freq <= 5925: ch = (freq-5000)//5
        elif freq >= 5945:         ch = (freq-5950)//5+1
        current["channel"] = ch or 0
    band = channel_to_band(current.get("channel",0), freq)
    current.update({"band":band,"freq_mhz":freq,
                    "ssid":current.get("ssid","<hidden>"),
                    "signal":current.get("signal",-100),
                    "width":current.get("width",20)})
    sec = current.get("security", set())
    current["security_str"] = "/".join(sorted(sec)) if sec else "Open"
    networks.append(current)

def scan_iw(iface: str) -> list:
    for cmd in [["iw","dev",iface,"scan","dump"],["iw","dev",iface,"scan"]]:
        try:
            out = subprocess.check_output(cmd,text=True,stderr=subprocess.PIPE,timeout=15)
            if out.strip(): break
        except: continue
    else: return []
    networks, current = [], {}
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"BSS\s+([0-9a-fA-F:]{17})", line)
        if m:
            if current: _finalize(current, networks)
            current = {"bssid": m.group(1).upper()}; continue
        if not current: continue
        for pat, key in [(r"SSID:\s*(.*)", "ssid"),
                         (r"freq:\s*(\d+)", "freq"),
                         (r"signal:\s*([-\d.]+)\s*dBm", "signal")]:
            mm = re.match(pat, line)
            if mm:
                val = mm.group(1).strip()
                current[key] = int(float(val)) if key in ("freq","signal") else (val or "<hidden>")
        m2 = re.match(r"DS Parameter set: channel\s+(\d+)", line)
        if m2: current["channel"] = int(m2.group(1))
        m3 = re.match(r"\* primary channel:\s*(\d+)", line)
        if m3: current["channel"] = int(m3.group(1))
        m4 = re.match(r"\* channel width:\s*(\d+)", line)
        if m4: current["width"] = int(m4.group(1))
        if "WPA2" in line or "RSN:" in line: current.setdefault("security",set()).add("WPA2")
        elif "WPA:" in line: current.setdefault("security",set()).add("WPA")
    if current: _finalize(current, networks)
    return networks

def scan_auto(iface: str) -> list:
    nets = scan_nmcli(iface)
    return nets if nets else scan_iw(iface)

# ──────────────────────────────────────────────────────────────
# Histórico de sinal
# ──────────────────────────────────────────────────────────────

signal_history: dict = defaultdict(lambda: deque([None]*GRAPH_WIDTH, maxlen=GRAPH_WIDTH))

def update_history(networks: list):
    seen = {n["bssid"]: n["signal"] for n in networks}
    for bssid in list(signal_history.keys()):
        signal_history[bssid].append(seen.get(bssid))
    for n in networks:
        if n["bssid"] not in signal_history:
            signal_history[n["bssid"]].append(n["signal"])

# ──────────────────────────────────────────────────────────────
# Gráfico de sinal em tempo real (Modo Foco)
# ──────────────────────────────────────────────────────────────

def _dbm_to_row(dbm, height=GRAPH_HEIGHT) -> int:
    clamped = max(SIGNAL_MIN, min(SIGNAL_MAX, dbm))
    ratio   = (clamped - SIGNAL_MIN) / (SIGNAL_MAX - SIGNAL_MIN)
    return height - 1 - int(ratio * (height-1))

def build_signal_graph(target: dict, history: deque, width: int, height: int = 28) -> Panel:
    """
    gping-style signal graph: thin line at top, no fill,
    dense dBm scale, occupies all available space.
    """
    h = max(8, height)
    w = max(20, width - 8)   # 8 chars para eixo Y

    # Aumentar o histórico se necessário
    samples_all = list(history)
    # Pegar as últimas w amostras
    samples = samples_all[-w:]
    # Preencher à esquerda com None se tiver menos dados que a largura
    if len(samples) < w:
        samples = [None] * (w - len(samples)) + samples

    # Grade vazia
    grid = [[" "] * w for _ in range(h)]

    # Linhas de referência horizontais leves (apenas nos labels do eixo Y)
    ref_dbm = list(range(-20, -101, -5))   # -20, -25, -30, ..., -100

    ref_rows = {}
    for dbm_ref in ref_dbm:
        row = _dbm_to_row(dbm_ref, h)
        if 0 <= row < h:
            ref_rows[row] = dbm_ref
            # Linha tracejada muito sutil apenas para referência
            for col in range(w):
                if grid[row][col] == " ":
                    grid[row][col] = "─" if col % 4 == 0 else " "

    # Plotar APENAS a linha de topo (estilo gping — sem preenchimento)
    prev_row = None
    prev_val = None
    for col, val in enumerate(samples):
        if val is None:
            prev_row = None
            prev_val = None
            continue
        row = max(0, min(h - 1, _dbm_to_row(val, h)))

        # Ponto principal — usa bloco horizontal duplo para linha mais grossa
        grid[row][col] = "▄"

        # Linha vertical de conexão entre amostras adjacentes
        if prev_row is not None and abs(prev_row - row) > 1:
            lo = min(prev_row, row) + 1
            hi = max(prev_row, row)
            for r in range(lo, hi):
                grid[r][col] = "│"

        prev_row = row
        prev_val = val

    # Montar linhas com eixo Y denso
    lines = []
    for r in range(h):
        # Label do eixo Y: mostra a cada linha que tem referência
        if r in ref_rows:
            label = f"{ref_rows[r]:>5}"
        else:
            label = "     "
        row_markup = f"[dim]{label}[/dim][bright_black]│[/bright_black]"

        for col in range(w):
            cell     = grid[r][col]
            sig_val  = samples[col] if col < len(samples) else None
            sc       = signal_color(sig_val) if sig_val is not None else "dim"
            if cell in ("▄", "│"):
                row_markup += f"[{sc}]{cell}[/{sc}]"
            elif cell in ("─",):
                row_markup += f"[grey23]{cell}[/grey23]"
            else:
                row_markup += " "
        lines.append(row_markup)

    # Eixo X
    lines.append(f"[dim]     └{'─' * w}[/dim]")
    pad = w - 5
    lines.append(f"[dim]      {'oldest':<{pad//2}}{'now':>{pad - pad//2}}[/dim]")

    # Estatísticas
    vals    = [v for v in samples_all if v is not None]
    sig     = target["signal"]
    avg     = int(sum(vals) / len(vals)) if vals else sig
    mn, mx  = (min(vals), max(vals)) if vals else (sig, sig)
    sc      = signal_color(sig)
    band_col = BAND_COLORS.get(target["band"], "white")

    title = (
        f"[bold white]{target['ssid']}[/bold white]  "
        f"[dim]{target['bssid']}[/dim]  "
        f"[{band_col}]{target['band']}[/{band_col}]  "
        f"CH [bold]{target['channel']}[/bold]  "
        f"{target.get('freq_mhz', 0)} MHz  "
        f"[{sc}]{sig} dBm[/{sc}]  "
        f"[dim]min[/dim] [red]{mn}[/red]  "
        f"[dim]avg[/dim] [yellow]{avg}[/yellow]  "
        f"[dim]max[/dim] [green]{mx}[/green] [dim]dBm[/dim]  "
        f"{signal_bar(sig)}"
    )
    return Panel(
        Text.from_markup("\n".join(lines)),
        title=title,
        border_style=sc,
        padding=(0, 0),
    )

def build_focus_details(target: dict) -> Panel:
    sc  = signal_color(target["signal"])
    sec = target.get("security_str","Open")
    sec_c = "red" if sec == "Open" else "green"
    bc  = BAND_COLORS.get(target["band"], "white")
    lines = [
        f"[dim]SSID[/dim]        [bold white]{target['ssid']}[/bold white]",
        f"[dim]BSSID[/dim]       [bright_yellow]{target['bssid']}[/bright_yellow]",
        f"[dim]Band[/dim]        [{bc}]{target['band']}[/{bc}]",
        f"[dim]Canal[/dim]       [bold cyan]{target['channel']}[/bold cyan]",
        f"[dim]Frequency[/dim]  [cyan]{target.get('freq_mhz',0)} MHz[/cyan]",
        f"[dim]Width[/dim]       {target.get('width',20)} MHz",
        f"[dim]Sinal[/dim]       [{sc}]{target['signal']} dBm[/{sc}]",
        f"[dim]Quality[/dim]    {signal_bar(target['signal'])}",
        f"[dim]Security[/dim]    [{sec_c}]{sec}[/{sec_c}]",
    ]
    return Panel(Text.from_markup("\n".join(lines)),
                 title="[bold]Details[/bold]", border_style="bright_black", padding=(0,1))

def build_focus_peers(target: dict, networks: list) -> Panel:
    same = [n for n in networks
            if n["bssid"] != target["bssid"]
            and n["channel"] == target["channel"]
            and n["band"] == target["band"]]
    if not same:
        content = "[dim]No networks on the same channel — no direct interference[/dim]"
    else:
        rows = []
        for n in sorted(same, key=lambda x: x["signal"], reverse=True):
            sc = signal_color(n["signal"])
            rows.append(
                f"[{sc}]{n['signal']:>4} dBm[/{sc}]  "
                f"[bold white]{n['ssid'][:22]:<22}[/bold white]  "
                f"[dim]{n['bssid']}[/dim]  "
                f"[dim]{n.get('security_str','?')}[/dim]"
            )
        content = "\n".join(rows)
    return Panel(Text.from_markup(content),
                 title=f"[bold yellow]Interferers CH {target['channel']} / {target['band']}[/bold yellow]",
                 border_style="bright_black", padding=(0,1))

# ──────────────────────────────────────────────────────────────
# UI — Modo Lista
# ──────────────────────────────────────────────────────────────

def build_table(networks: list, band_filter: str, sort_by: str, selected_idx: int) -> Table:
    visible = [n for n in networks if band_filter == "ALL" or n["band"] == band_filter]
    key_map = {
        "signal":  lambda n: n["signal"],
        "channel": lambda n: n["channel"],
        "ssid":    lambda n: n["ssid"].lower(),
        "bssid":   lambda n: n["bssid"],
    }
    visible.sort(key=key_map.get(sort_by, key_map["signal"]), reverse=(sort_by=="signal"))

    table = Table(box=box.SIMPLE_HEAVY, border_style="bright_black",
                  header_style="bold bright_white on grey15",
                  show_edge=True, padding=(0,1), expand=True)
    table.add_column("#",         style="dim",           width=4,  justify="right")
    table.add_column("SSID",      style="bold white",    min_width=16, max_width=30, no_wrap=True)
    table.add_column("BSSID",     style="bright_yellow", width=19)
    table.add_column("CH",        style="bold cyan",     width=4,  justify="center")
    table.add_column("MHz",       style="cyan",          width=6,  justify="right")
    table.add_column("BW",        style="dim cyan",      width=5,  justify="center")
    table.add_column("Band",      width=5,  justify="center")
    table.add_column("Signal",    width=8,  justify="right")
    table.add_column("Quality", width=22)
    table.add_column("Cong.",     width=6,  justify="center")
    table.add_column("Sec.",      width=10)

    for i, n in enumerate(visible, 1):
        sig  = n["signal"]
        band = n["band"]
        ch   = n["channel"]
        freq = n.get("freq_mhz",0)
        cong = channel_congestion(networks, ch, band)
        sc   = signal_color(sig)
        bc   = BAND_COLORS.get(band,"white")

        cong_cell = (f"[green]● {cong}[/green]" if cong<=1
                     else f"[yellow]◑ {cong}[/yellow]" if cong<=3
                     else f"[red]○ {cong}[/red]")

        is_sel     = (i-1 == selected_idx)
        row_style  = "on grey19" if is_sel else ""
        num_str    = f"[bold cyan]▶{i}[/bold cyan]" if is_sel else str(i)

        table.add_row(
            num_str, n["ssid"], n["bssid"],
            str(ch) if ch else "?",
            str(freq) if freq else "?",
            f"{n.get('width',20)}M",
            f"[{bc}]{band}[/{bc}]",
            f"[{sc}]{sig} dBm[/{sc}]",
            signal_bar(sig),
            cong_cell,
            n.get("security_str","?"),
            style=row_style,
        )
    return table

def build_channel_map(networks: list) -> Panel:
    ch_count: dict = defaultdict(int)
    for n in networks:
        ch_count[(n["band"], n["channel"])] += 1
    lines_24, lines_5 = [], []
    for ch in range(1, 14):
        cnt   = ch_count.get(("2.4G",ch), 0)
        bar   = "█" * min(cnt, 8)
        color = "green" if cnt<=1 else ("yellow" if cnt<=3 else "red")
        lines_24.append(f"[dim]CH{ch:>2}[/dim] [{color}]{bar:<8}[/{color}] [dim]{cnt}[/dim]")
    for ch in [36,40,44,48,52,56,60,64,100,104,108,112,116,120,
               124,128,132,136,140,144,149,153,157,161,165]:
        cnt = ch_count.get(("5G",ch),0)
        if cnt == 0 and ch > 64: continue
        bar   = "█" * min(cnt, 8)
        color = "cyan" if cnt<=1 else ("yellow" if cnt<=3 else "red")
        lines_5.append(f"[dim]CH{ch:>3}[/dim] [{color}]{bar:<8}[/{color}] [dim]{cnt}[/dim]")
    col1 = "[bold green]2.4 GHz[/bold green]\n" + "\n".join(lines_24) if lines_24 else ""
    col2 = "[bold cyan]5 GHz[/bold cyan]\n"     + "\n".join(lines_5)  if lines_5  else ""
    content = Columns([col1, col2], equal=False, expand=True) if (col1 or col2) else Text("No data")
    return Panel(content, title="[bold]Channel Map[/bold]",
                 border_style="bright_black", padding=(0,1))

def build_suggestions(networks: list) -> Panel:
    s24 = suggest_channel(networks, "2.4G")
    s5  = suggest_channel(networks, "5G")
    txt = (f"[bold green]2.4 GHz[/bold green]  Suggested channel: [bold white]{s24}[/bold white]\n"
           f"[bold cyan]5 GHz  [/bold cyan]  Suggested channel: [bold white]{s5}[/bold white]")
    return Panel(txt, title="[bold]Anti-Interference Suggestions[/bold]",
                 border_style="bright_black", padding=(0,1))

def build_stats(networks, iface, elapsed, mode, sel_idx, n_vis) -> Panel:
    total  = len(networks)
    n_24   = sum(1 for n in networks if n["band"]=="2.4G")
    n_5    = sum(1 for n in networks if n["band"]=="5G")
    n_6    = sum(1 for n in networks if n["band"]=="6G")
    n_open = sum(1 for n in networks if n.get("security_str")=="Open")
    best   = max(networks, key=lambda n: n["signal"]) if networks else None
    best_s = (f"[bold white]{best['ssid']}[/bold white] [green]{best['signal']} dBm[/green]"
              if best else "—")
    mode_s = "[bold cyan]● FOCO[/bold cyan]" if mode=="focus" else "[dim]list[/dim]"
    nav_s  = f"[dim] {sel_idx+1}/{n_vis}[/dim]" if n_vis else ""
    txt = (f"Interface: [bold yellow]{iface}[/bold yellow]   "
           f"Total: [bold]{total}[/bold]   "
           f"[green]2.4G:{n_24}[/green] [cyan]5G:{n_5}[/cyan] [magenta]6G:{n_6}[/magenta]   "
           f"Open:[red]{n_open}[/red]   "
           f"Best: {best_s}   "
           f"Scan:[dim]{elapsed:.1f}s[/dim]   "
           f"{mode_s}{nav_s}   "
           f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]")
    return Panel(txt, border_style="bright_black", padding=(0,1))

HELP_LIST = (
    "[dim] [bold white]↑↓[/bold white]/[bold white]jk[/bold white] move  "
    "[bold white]Enter[/bold white]/[bold white]f[/bold white] focus  "
    "[bold white]s[/bold white] signal  [bold white]c[/bold white] channel  "
    "[bold white]n[/bold white] ssid  [bold white]2[/bold white] 2.4G  "
    "[bold white]5[/bold white] 5G  [bold white]a[/bold white] all  "
    "[bold white]m[/bold white] map  [bold white]q[/bold white] quit[/dim]"
)
HELP_FOCUS = (
    "[dim] [bold cyan]Esc[/bold cyan]/[bold cyan]b[/bold cyan] back  "
    "[bold white]↑↓[/bold white]/[bold white]jk[/bold white] switch network  "
    "[bold white]q[/bold white] quit[/dim]"
)

# ──────────────────────────────────────────────────────────────
# Input não-bloqueante (sem travar o loop de scan)
# ──────────────────────────────────────────────────────────────

def read_key_nonblock(fd: int) -> str | None:
    """Lê uma tecla/sequência sem bloquear. Retorna None se não há input."""
    import select, tty, termios
    r, _, _ = select.select([sys.stdin], [], [], 0.0)
    if not r:
        return None
    ch = os.read(fd, 1).decode("utf-8", errors="replace")
    if ch == "\x1b":
        r2, _, _ = select.select([sys.stdin], [], [], 0.05)
        if r2:
            rest = os.read(fd, 4).decode("utf-8", errors="replace")
            return ch + rest
    return ch

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WiFi Analyzer CLI")
    parser.add_argument("-i","--iface",   default=None)
    parser.add_argument("-r","--refresh", type=float, default=1.0)
    parser.add_argument("-f","--filter",  default="ALL", choices=["ALL","2.4G","5G","6G"])
    parser.add_argument("--sort",         default="signal",
                        choices=["signal","channel","ssid","bssid"])
    parser.add_argument("--debug",        action="store_true")
    args = parser.parse_args()

    # ── Debug mode (sem root, sem tty raw) ──────────────────
    if args.debug:
        iface_d = args.iface or (get_interfaces() or ["wlo1"])[0]
        print(f"\n=== debug (iface={iface_d}) ===")
        for rescan in ("no","yes"):
            print(f"\n-- nmcli rescan={rescan} --")
            try:
                r = subprocess.run(
                    ["nmcli","-t","-f","BSSID,SSID,MODE,CHAN,FREQ,RATE,SIGNAL,BARS,SECURITY",
                     "device","wifi","list","ifname",iface_d,"--rescan",rescan],
                    capture_output=True, text=True, timeout=25)
                print("OUT:", r.stdout[:2000] or "(empty)")
                print("ERR:", r.stderr[:300]  or "(empty)")
            except Exception as e: print("ERRO:", e)
        print("\n-- iw scan dump --")
        try:
            r = subprocess.run(["iw","dev",iface_d,"scan","dump"],
                               capture_output=True, text=True, timeout=10)
            print(r.stdout[:1000] or "(vazio)")
        except Exception as e: print("ERRO:", e)
        sys.exit(0)

    # ── Root check ───────────────────────────────────────────
    if os.geteuid() != 0:
        print("\n[ERRO] Requer root:\n  sudo python3 wifi_analyzer.py\n")
        sys.exit(1)

    # ── Interface ────────────────────────────────────────────
    iface = args.iface
    if not iface:
        ifaces = get_interfaces()
        if not ifaces:
            print("[ERROR] No wireless interface found."); sys.exit(1)
        iface = ifaces[0]

    # ── Estado ───────────────────────────────────────────────
    band_filter = args.filter
    sort_by     = args.sort
    show_map    = True
    refresh     = args.refresh
    mode        = "list"
    sel_idx     = 0
    focus_bssid = None
    networks: list = []
    elapsed   = 0.0

    def get_visible():
        v = [n for n in networks if band_filter=="ALL" or n["band"]==band_filter]
        km = {"signal": lambda n: n["signal"], "channel": lambda n: n["channel"],
              "ssid": lambda n: n["ssid"].lower(), "bssid": lambda n: n["bssid"]}
        v.sort(key=km.get(sort_by, km["signal"]), reverse=(sort_by=="signal"))
        return v

    def render():
        nonlocal focus_bssid
        visible = get_visible()
        n_vis   = len(visible)
        s_idx   = min(sel_idx, n_vis-1) if n_vis else 0
        layout  = Layout()

        if mode == "focus" and focus_bssid:
            target = next((n for n in visible if n["bssid"]==focus_bssid), None)
            if not target and visible:
                target = visible[s_idx] if s_idx < len(visible) else visible[0]

            layout.split_column(
                Layout(name="header", size=8),
                Layout(name="stats",  size=3),
                Layout(name="graph",  ratio=1),
                Layout(name="bottom", size=10),
                Layout(name="help",   size=3),
            )
            layout["header"].update(Align.center(build_header_text()))
            layout["stats"].update(build_stats(networks,iface,elapsed,"focus",s_idx,n_vis))
            if target:
                tw = console.width
                ch_height = max(10, console.height - 30)
                layout["graph"].update(build_signal_graph(target, signal_history[target["bssid"]], tw - 2, ch_height))
                layout["bottom"].split_row(
                    Layout(build_focus_details(target), ratio=1),
                    Layout(build_focus_peers(target, networks), ratio=2),
                )
            else:
                layout["graph"].update(Panel("[dim]Rede não encontrada[/dim]", border_style="red"))
                layout["bottom"].update(Panel(""))
            layout["help"].update(Align.center(Text.from_markup(HELP_FOCUS)))
        else:
            bottom_size = 8 if show_map else 0
            layout.split_column(
                Layout(name="header", size=8),
                Layout(name="stats",  size=3),
                Layout(name="table",  ratio=1),
                Layout(name="bottom", size=bottom_size, visible=show_map),
                Layout(name="help",   size=3),
            )
            layout["header"].update(Align.center(build_header_text()))
            layout["stats"].update(build_stats(networks,iface,elapsed,"list",s_idx,n_vis))
            layout["table"].update(build_table(networks,band_filter,sort_by,s_idx))
            if show_map:
                layout["bottom"].split_row(
                    Layout(build_channel_map(networks)),
                    Layout(build_suggestions(networks)),
                )
            layout["help"].update(Align.center(Text.from_markup(HELP_LIST)))
        return layout

    # ── Configurar terminal raw uma só vez ───────────────────
    import tty, termios, select
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    console = Console()

    try:
        tty.setcbreak(fd)   # raw input — restaurado no finally

        with Live(render(), console=console, screen=True, refresh_per_second=4) as live:
            next_scan = 0.0

            while True:
                now = time.time()

                # Scan quando chegou a hora
                if now >= next_scan:
                    t0       = time.time()
                    networks = scan_auto(iface)
                    elapsed  = time.time() - t0
                    update_history(networks)
                    next_scan = time.time() + refresh
                    live.update(render())

                # Processar input não-bloqueante
                key = read_key_nonblock(fd)
                if key is None:
                    time.sleep(0.05)
                    continue

                visible = get_visible()
                n_vis   = len(visible)

                if mode == "list":
                    if   key in ("\x1b[A","k","K"):   sel_idx = max(0, sel_idx-1)
                    elif key in ("\x1b[B","j","J"):   sel_idx = min(n_vis-1, sel_idx+1) if n_vis else 0
                    elif key in ("\r","\n","f","F"):
                        if visible and sel_idx < n_vis:
                            focus_bssid = visible[sel_idx]["bssid"]
                            mode = "focus"
                    elif key.lower() == "q": break
                    elif key.lower() == "s": sort_by = "signal"
                    elif key.lower() == "c": sort_by = "channel"
                    elif key.lower() == "n": sort_by = "ssid"
                    elif key == "2": band_filter = "2.4G"
                    elif key == "5": band_filter = "5G"
                    elif key == "6": band_filter = "6G"
                    elif key.lower() == "a": band_filter = "ALL"
                    elif key.lower() == "m": show_map = not show_map
                elif mode == "focus":
                    if   key in ("\x1b","b","B","\x1b\x1b"): mode = "list"
                    elif key in ("\x1b[A","k","K"):
                        sel_idx = max(0, sel_idx-1)
                        if visible: focus_bssid = visible[min(sel_idx,n_vis-1)]["bssid"]
                    elif key in ("\x1b[B","j","J"):
                        sel_idx = min(n_vis-1, sel_idx+1) if n_vis else 0
                        if visible: focus_bssid = visible[min(sel_idx,n_vis-1)]["bssid"]
                    elif key.lower() == "q": break

                live.update(render())

    finally:
        # Sempre restaura o terminal — evita o "Saindo..." por KeyboardInterrupt
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print("\nGoodbye!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass   # terminal já restaurado no finally
