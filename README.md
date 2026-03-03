# TAM App

Internal tooling for TAM configuration, validation, and data management.

## Installation

Open **Terminal** and run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/liorFeigenbaum/TamApp/main/TamApp_Install.command)
```

This downloads and runs the installer directly — no file to download, no macOS security warnings.

### What the installer does
1. Checks that git and Python 3 are installed
2. Clones the repository to `~/TamApp`
3. Creates a Python virtual environment
4. Installs all dependencies

Once the app opens in your browser, click **"Create Desktop Launcher"** in the top-right corner to add a TAM App icon to your Desktop.

## Requirements

- macOS
- Python 3 — install from [python.org](https://python.org) if missing
- git — install Xcode Command Line Tools if missing (`xcode-select --install`)

## Launching after install

Double-click the **TAM App** icon on your Desktop. It will start the server automatically and open the app in your browser.
