# iRacing Telemetry Collector - Project Plan

## Project Goal

Build a **single Windows .exe** that:
1. Runs in the background (system tray) and automatically detects iRacing telemetry
2. Parses `.ibt` telemetry files as they are generated
3. Exports a CSV file **per lap** matching the format in `OutputDataExample.csv`
4. Saves CSVs to a local folder — no database, no server, no browser UI

**This is a self-contained desktop tool. No backend, no database, no web UI.**

---

## Research Summary

### iRacing Telemetry Access Methods

| Method | Update Rate | Lat/Lon Available | Requires iRacing Running |
|--------|-------------|-------------------|--------------------------|
| **Live SDK** (shared memory) | 60 Hz | NO (disk-only) | Yes |
| **IBT Files** (.ibt telemetry files) | 60 Hz | YES | No (post-session) |
| **Session YAML** | On change | N/A | Yes |

**Critical finding**: `Lat` and `Lon` (GPS coordinates) are **only available in IBT files**, not through the live shared memory API. Since the target CSV requires these fields, we must parse IBT files as the primary data source.

### Required CSV Fields & SDK Variable Mapping

| CSV Column | iRacing SDK Variable | Type | Notes |
|------------|---------------------|------|-------|
| Speed | `Speed` | float | GPS vehicle speed (m/s) |
| LapDistPct | `LapDistPct` | float | Percentage distance around lap |
| Lat | `Lat` | double | **IBT only** - latitude |
| Lon | `Lon` | double | **IBT only** - longitude |
| Brake | `Brake` | float | 0=released, 1=max force |
| Throttle | `Throttle` | float | 0=off, 1=full |
| RPM | `RPM` | float | Engine RPM |
| SteeringWheelAngle | `SteeringWheelAngle` | float | Radians |
| Gear | `Gear` | int | -1=R, 0=N, 1..n=gear |
| Clutch | `Clutch` | float | 0=disengaged, 1=engaged |
| ABSActive | `BrakeABSactive` | bool | ABS reducing brake force |
| DRSActive | `DRS_Status` | int | 0=inactive, 3=active (map to bool) |
| LatAccel | `LatAccel` | float | Lateral accel (m/s²) |
| LongAccel | `LongAccel` | float | Longitudinal accel (m/s²) |
| VertAccel | `VertAccel` | float | Vertical accel (m/s²) |
| Yaw | `Yaw` | float | Yaw orientation (rad) |
| YawRate | `YawRate` | float | Yaw rate (rad/s) |
| PositionType | Session-derived | int | Race position type (from session info) |

### Key Open-Source Projects

| Project | Language | What We Use From It |
|---------|----------|-------------------|
| [pyirsdk](https://github.com/kutu/pyirsdk) | Python | **Core dependency** - reads IBT files |
| [Mu](https://github.com/patrickmoore/Mu) | - | Reference for background IBT file monitoring pattern |

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────┐
│              Single Python EXE                   │
│                                                  │
│  ┌──────────────┐     ┌───────────────────────┐ │
│  │ System Tray   │     │   File Watcher        │ │
│  │ (pystray)     │     │   (watchdog)          │ │
│  │               │     │                       │ │
│  │ • Status icon │     │ Monitors:             │ │
│  │ • Open output │     │ ~/Documents/iRacing/  │ │
│  │ • Settings    │     │   Telemetry/*.ibt     │ │
│  │ • Quit        │     └───────────┬───────────┘ │
│  └──────────────┘                  │             │
│                                    ▼             │
│                        ┌───────────────────────┐ │
│                        │   IBT Parser          │ │
│                        │   (pyirsdk)           │ │
│                        │                       │ │
│                        │ • Extract session info │ │
│                        │ • Read 60Hz telemetry │ │
│                        │ • Split into laps     │ │
│                        └───────────┬───────────┘ │
│                                    │             │
│                                    ▼             │
│                        ┌───────────────────────┐ │
│                        │   CSV Exporter        │ │
│                        │                       │ │
│                        │ • One CSV per lap     │ │
│                        │ • 18 columns          │ │
│                        │ • Matches example fmt │ │
│                        └───────────┬───────────┘ │
│                                    │             │
│                                    ▼             │
│                        ┌───────────────────────┐ │
│                        │   Output Folder       │ │
│                        │   (local disk)        │ │
│                        │                       │ │
│                        │ ~/Documents/iRacing/  │ │
│                        │   TelemetryCSV/       │ │
│                        │   ├── track_car_date/ │ │
│                        │   │   ├── lap_01.csv  │ │
│                        │   │   ├── lap_02.csv  │ │
│                        │   │   └── ...         │ │
│                        └───────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Data Flow

1. **iRacing** writes `.ibt` files to `~/Documents/iRacing/Telemetry/` during sessions
2. **File Watcher** (using `watchdog`) monitors the telemetry folder for new/modified `.ibt` files
3. **IBT Parser** (using `pyirsdk`) reads the IBT file and extracts:
   - Session metadata (track, car, date, session type) from YAML header
   - Per-tick telemetry data (all 18 CSV columns) at 60Hz
   - Lap boundaries using `LapDistPct` rollover detection
4. **CSV Exporter** writes one CSV file per lap directly to disk
5. **System Tray** shows status and provides quick access to the output folder

### Why This Architecture?

- **IBT-based** (not live SDK): Because Lat/Lon GPS coordinates are only available in IBT files
- **No database**: CSVs are the output format — storing in a DB first just adds complexity. Parse IBT → write CSV directly.
- **No web UI / no backend**: A system tray icon with folder access is all that's needed. The user consumes the CSVs in their own tools.
- **Single EXE**: PyInstaller bundles everything into one downloadable file. No installer, no dependencies, no setup.
- **Python**: `pyirsdk` is the most mature iRacing SDK. Python has excellent libraries for file watching and CSV generation.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **IBT Parsing** | `pyirsdk` | Mature iRacing SDK, reads IBT files |
| **File Watching** | `watchdog` | Cross-platform filesystem event monitoring |
| **CSV Export** | Python `csv` module | Standard library, matches output format exactly |
| **System Tray** | `pystray` + `Pillow` | Lightweight system tray with icon and menu |
| **Logging** | Python `logging` | Built-in, configurable log levels |
| **Packaging** | `PyInstaller` | Single-file Windows EXE, no install needed |

---

## Project Structure

```
iracing-telemetry/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point: starts tray + watcher
│   ├── config.py            # Paths, settings, defaults
│   ├── ibt_parser.py        # IBT file parsing with pyirsdk
│   ├── csv_exporter.py      # Per-lap CSV writer
│   ├── file_watcher.py      # Watchdog-based IBT folder monitor
│   ├── tray.py              # System tray icon and menu (pystray)
│   └── variable_map.py      # SDK variable name → CSV column mapping
├── assets/
│   └── icon.ico             # System tray icon
├── tests/
│   ├── test_ibt_parser.py
│   ├── test_csv_exporter.py
│   └── test_file_watcher.py
├── OutputDataExample.csv    # Reference CSV format
├── requirements.txt
├── build.spec               # PyInstaller spec for single-file EXE
├── PLAN.md                  # This file
└── README.md
```

---

## Implementation Phases

### Phase 1: Core IBT Parser
**Goal**: Parse IBT files and extract all 18 CSV columns in memory, split into laps.

1. Set up Python project with `pyirsdk`
2. Implement `ibt_parser.py`:
   - Open IBT files using `pyirsdk.IBT`
   - Extract session YAML metadata (track, car, date, session type)
   - Read all telemetry ticks and extract the 18 required variables
   - Handle variable name mapping (`BrakeABSactive` → `ABSActive`, `DRS_Status` → `DRSActive`)
   - Split telemetry into laps using `LapDistPct` rollover detection
   - Return structured data: session info + list of laps (each lap = list of dicts)
3. Write tests with sample IBT data

### Phase 2: CSV Export
**Goal**: Write per-lap CSVs matching `OutputDataExample.csv` exactly.

1. Implement `csv_exporter.py`:
   - Accept parsed lap data (list of dicts from Phase 1)
   - Write CSV with exact column headers and formatting
   - Create output folder structure: `TelemetryCSV/{track}_{car}_{date}/{session_type}_lap_{N}.csv`
   - Match number formatting (float precision, boolean as `true`/`false`)
2. Implement end-to-end pipeline: IBT file → parse → CSV files on disk
3. Write tests comparing output against `OutputDataExample.csv` format

### Phase 3: File Watcher & System Tray
**Goal**: Auto-detect new IBT files and process them. System tray for status.

1. Implement `file_watcher.py` using `watchdog`:
   - Monitor iRacing telemetry folder
   - Debounce events (IBT files are written continuously during sessions)
   - Wait for file to be finalized before processing
   - Skip files already processed (track by filename in a local `.processed` log)
2. Implement `tray.py` using `pystray`:
   - System tray icon with status (idle / watching / processing)
   - Right-click menu: Open output folder, Reprocess all, Settings, Quit
   - First-run: scan and process all existing IBT files
3. Implement `main.py` entry point tying everything together

### Phase 4: Packaging as Single EXE
**Goal**: One downloadable `.exe` file that just works.

1. Create `build.spec` for PyInstaller single-file mode
2. Bundle all dependencies (pyirsdk, watchdog, pystray, Pillow)
3. Include icon asset
4. Test on clean Windows machine (no Python installed)
5. Optimize EXE size where possible

---

## Key Technical Decisions

### IBT Parsing vs Live Telemetry
We use **IBT file parsing** because:
- `Lat`/`Lon` GPS coordinates are **only available in IBT files**
- IBT files are automatically generated by iRacing
- Data is complete and finalized (no dropped frames)
- Can process historical sessions retroactively

### No Database
- The end product is CSV files — no reason to store data in SQLite first
- Parsing is fast enough to do on-the-fly (IBT → memory → CSV)
- A `.processed` text file tracks which IBT files have been handled
- Simpler architecture = fewer bugs, smaller EXE, easier maintenance

### No Web UI
- The user needs CSV files, not a dashboard
- System tray + file explorer is sufficient for the UX
- Eliminates the entire Electron/React/FastAPI stack
- Massively reduces bundle size and complexity

### Single EXE Distribution
- PyInstaller `--onefile` mode creates a single portable `.exe`
- No installer needed — download and double-click
- User can place it anywhere (Desktop, startup folder, etc.)
- No Python installation required on the target machine

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Lat/Lon not in all IBT files | CSV output incomplete | Validate on parse; skip or flag laps without GPS |
| IBT file format changes | Parser breaks | Pin pyirsdk version; add format version check |
| Large telemetry data (60Hz × long sessions) | Slow processing | Process in streaming fashion; one lap at a time |
| PyInstaller EXE size | Large download (~30-50MB) | Acceptable; much smaller than Electron alternative |
| iRacing telemetry folder varies by user | Watcher points to wrong path | Configurable path via tray settings; auto-detect default |
| Antivirus flags PyInstaller EXE | User can't run app | Sign the EXE; provide documentation |

---

## Output CSV Naming Convention

```
~/Documents/iRacing/TelemetryCSV/
└── {TrackName}_{CarName}_{YYYY-MM-DD_HH-MM}/
    ├── practice_lap_01.csv
    ├── practice_lap_02.csv
    ├── qualify_lap_01.csv
    ├── race_lap_01.csv
    ├── race_lap_02.csv
    └── ...
```

Each CSV contains 60Hz telemetry for a single lap with the 18 columns from `OutputDataExample.csv`.
