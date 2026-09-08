# Real-Time Translator

A small real-time translation demo that captures audio, transcribes, and displays translations in a simple Tkinter UI.

## Requirements
- Python 3.11+ (project uses a local virtual environment)
- See `requirements.txt` for Python dependencies

## Setup
1. Create and activate a virtual environment (recommended):

```bash
/usr/bin/python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

## Run
Start the GUI application:

```bash
python -m ui.app
```

If you prefer to run the script directly:

```bash
python ui/app.py
```

## Notes & Troubleshooting
- Ensure you run commands from the project root directory.
- If you see `ModuleNotFoundError: No module named 'sounddevice'`, install dependencies into the `.venv` as shown above.
- The UI package is `ui` (lowercase). If you had an older `UI/` folder, ensure it's removed or renamed.

## Development
- Key files:
	- UI window and styles: [ui/window.py](ui/window.py#L1-L1)
	- App entrypoint: [ui/app.py](ui/app.py#L1-L1)
	- Main translator entry: [main.py](main.py#L1-L1)


***
Generated README with quick run/setup instructions.
