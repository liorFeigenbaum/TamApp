#!/bin/bash
# ==============================================================================
#  TAM App Installer
#  Double-click this file to install TAM App on your Mac.
# ==============================================================================

# ── Terminal title ──────────────────────────────────────────────────────────
echo -ne "\033]0;TAM App Installer\007"

# ── Change to the directory this script lives in ───────────────────────────
cd "$(dirname "$0")"

# ── Colours ────────────────────────────────────────────────────────────────
R='\033[0;31m'   # red
G='\033[0;32m'   # green
Y='\033[1;33m'   # yellow
B='\033[0;34m'   # blue
T='\033[0;36m'   # teal/cyan
N='\033[0m'      # reset

REPO_URL="https://github.com/liorFeigenbaum/TamApp.git"
  INSTALL_DIR="$HOME/TamApp"
PORT=5001
STEPS=6
STEP=0

# ── Helpers ─────────────────────────────────────────────────────────────────
step() {
    STEP=$((STEP+1))
    echo ""
    echo -e "${T}── Step ${STEP}/${STEPS}: $1${N}"
    echo ""
}
ok()   { echo -e "  ${G}✅  $1${N}"; }
warn() { echo -e "  ${Y}⚠️   $1${N}"; }
info() { echo -e "  ${B}ℹ   $1${N}"; }
fail() {
    echo ""
    echo -e "  ${R}❌  ERROR: $1${N}"
    echo ""
    echo "  Please contact your TAM team administrator for help."
    echo ""
    read -rp "  Press Enter to close…"
    exit 1
}
hr() { echo ""; echo "  ──────────────────────────────────────────────"; echo ""; }

# ── Banner ──────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${T}  ╔══════════════════════════════════════════╗${N}"
echo -e "${T}  ║          TAM App  ·  Setup v1.0          ║${N}"
echo -e "${T}  ╚══════════════════════════════════════════╝${N}"
echo ""
echo "  This installer will:"
echo "    1. Check prerequisites  (git, python3)"
echo "    2. Clone the TAM App repository"
echo "    3. Set up a Python virtual environment"
echo "    4. Install dependencies"
echo "    5. Generate the app icon"
echo "    6. Add TAM App to your Desktop"
echo ""
read -rp "  Press Enter to begin…"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Prerequisites
# ══════════════════════════════════════════════════════════════════════════════
step "Checking prerequisites"

# macOS check
[[ "$OSTYPE" == darwin* ]] || fail "This installer is for macOS only."
ok "macOS detected"

# git
if ! command -v git &>/dev/null; then
    warn "git not found — launching Xcode Command Line Tools installer…"
    xcode-select --install 2>/dev/null
    echo ""
    echo "  After the Xcode tools finish installing, please re-run this script."
    read -rp "  Press Enter to close…"
    exit 1
fi
ok "git $(git --version | awk '{print $3}') found"

# python3
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done
[[ -n "$PYTHON" ]] || fail "Python 3 not found. Install from https://python.org then re-run."
PY_VER=$("$PYTHON" --version 2>&1 | awk '{print $2}')
ok "Python $PY_VER found ($PYTHON)"

# pip / venv
"$PYTHON" -m pip --version &>/dev/null || fail "pip is not available for $PYTHON."
ok "pip available"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Clone (or update) repository
# ══════════════════════════════════════════════════════════════════════════════
step "Cloning TAM App repository"

if [ -d "$INSTALL_DIR/.git" ]; then
    warn "TAM App is already installed at $INSTALL_DIR."
    echo ""
    read -rp "  (u) Update existing  /  (r) Re-install fresh  /  (s) Skip clone  [u/r/s]: " -n 1 CHOICE
    echo ""
    case "$CHOICE" in
        r|R)
            info "Removing existing installation…"
            rm -rf "$INSTALL_DIR"
            info "Cloning fresh copy…"
            git clone "$REPO_URL" "$INSTALL_DIR" \
                || fail "Clone failed. Check your GitHub access and try again."
            ok "Fresh clone complete → $INSTALL_DIR"
            ;;
        s|S)
            ok "Skipping clone — using existing files."
            ;;
        *)
            info "Updating existing installation…"
            git -C "$INSTALL_DIR" pull \
                || warn "Pull failed — continuing with existing files."
            ok "Repository updated."
            ;;
    esac
else
    info "Cloning from $REPO_URL …"
    info "(You may be prompted for GitHub credentials)"
    echo ""
    git clone "$REPO_URL" "$INSTALL_DIR" \
        || fail "Clone failed. Make sure you have access to the GitHub repo."
    ok "Cloned to $INSTALL_DIR"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Virtual environment
# ══════════════════════════════════════════════════════════════════════════════
step "Setting up Python virtual environment"

VENV_DIR="$INSTALL_DIR/.venv"

if [ -d "$VENV_DIR" ]; then
    ok "Virtual environment already exists — reusing."
else
    info "Creating virtual environment at $VENV_DIR …"
    "$PYTHON" -m venv "$VENV_DIR" \
        || fail "Could not create virtual environment."
    ok "Virtual environment created."
fi

# Activate
source "$VENV_DIR/bin/activate" || fail "Could not activate virtual environment."
ok "Virtual environment activated."

info "Upgrading pip…"
pip install --upgrade pip --quiet 2>/dev/null
ok "pip up to date."

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Install dependencies
# ══════════════════════════════════════════════════════════════════════════════
step "Installing Python dependencies"
echo ""
info "Installing packages — this can take a few minutes on first run…"
echo ""

REQ_FILE="$INSTALL_DIR/requirements.txt"

if [ -f "$REQ_FILE" ]; then
    # Try full install first; fall back to core if heavy system deps fail
    if pip install -r "$REQ_FILE" 2>&1 | tee /tmp/tamapp_pip.log | grep -q "ERROR"; then
        warn "Some packages failed (likely system-level libs like pyodbc/pymssql)."
        warn "Installing core web + data packages only…"
        echo ""
        CORE="flask gunicorn pandas numpy requests PyYAML Werkzeug Jinja2 boto3 reportlab"
        for pkg in $CORE; do
            if pip install "$pkg" --quiet 2>/dev/null; then
                ok "$pkg"
            else
                warn "$pkg  (skipped)"
            fi
        done
    else
        ok "All packages installed successfully."
    fi
else
    warn "requirements.txt not found — installing core packages only."
    pip install flask gunicorn pandas numpy Pillow --quiet
    ok "Core packages installed."
fi

# ══════════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════════
hr
echo -e "${G}  ╔══════════════════════════════════════════╗${N}"
echo -e "${G}  ║         ✅  Setup Complete!              ║${N}"
echo -e "${G}  ╚══════════════════════════════════════════╝${N}"
echo ""
echo "  TAM App is installed at: $INSTALL_DIR"
echo ""
echo "  👉  Once the app opens, click 'Create Desktop Launcher' (top-right)"
echo "      to add a TAM App icon to your Desktop."
echo ""
read -rp "  Launch TAM App now? [Y/n] " -n 1 LAUNCH
echo ""
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
    cd "$INSTALL_DIR"
    source .venv/bin/activate 2>/dev/null || true
    export PATH="$INSTALL_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
    nohup gunicorn --config gunicorn.conf.py app:app > /tmp/tamapp.log 2>&1 &
    info "Starting server…"
    i=0
    while [ $i -lt 15 ]; do
        sleep 1
        /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t &>/dev/null && break
        i=$((i+1))
    done
    open "http://localhost:$PORT"
fi
echo ""
echo "  Setup complete. You may close this window."
echo ""
