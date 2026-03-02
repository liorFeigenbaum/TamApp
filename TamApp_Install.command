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
        CORE="flask gunicorn pandas numpy requests PyYAML Werkzeug Jinja2 boto3 Pillow"
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

# Make sure Pillow is available (needed for icon)
python -c "from PIL import Image" 2>/dev/null \
    || pip install Pillow --quiet

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Generate icon
# ══════════════════════════════════════════════════════════════════════════════
step "Generating app icon"

ICONSET_DIR="${TMPDIR%/}/TamAppInstall_$$/TamApp.iconset"
ICNS_PATH="${TMPDIR%/}/TamAppInstall_$$/TamApp.icns"
mkdir -p "$ICONSET_DIR"
export TAM_ICONSET_DIR="$ICONSET_DIR"

info "Drawing T-monogram badge…"

python - <<'PYEOF'
from PIL import Image, ImageDraw
import os, sys

ICONSET = os.environ["TAM_ICONSET_DIR"]
os.makedirs(ICONSET, exist_ok=True)

# OneBeat brand colours
BG_CARD = (26,  42,  58)   # #1A2A3A  navy
TEAL    = (31,  108, 109)  # #1F6C6D
CORAL   = (253, 96,  74)   # #FD604A
BORDER  = (31,  50,  72)   # #1F3248

def make_icon(size):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s    = size
    pad  = s * 0.04
    r    = int(s * 0.18)

    # Background rounded square
    draw.rounded_rectangle(
        [pad, pad, s - pad, s - pad],
        radius=r, fill=BG_CARD, outline=BORDER, width=max(2, int(s * 0.012))
    )

    # Teal top accent bar
    bar_h = int(s * 0.045)
    draw.rounded_rectangle([pad, pad, s - pad, pad + bar_h], radius=r, fill=TEAL)
    draw.rectangle([pad, pad + bar_h // 2, s - pad, pad + bar_h], fill=BG_CARD)

    cx, cy = s / 2, s / 2

    # Bold geometric "T"
    t_bar_w  = s * 0.60
    t_bar_h  = s * 0.13
    t_stem_w = s * 0.19
    t_stem_h = s * 0.36
    t_top    = cy - (t_bar_h + t_stem_h) / 2 - s * 0.02

    draw.rectangle([cx - t_bar_w/2, t_top,
                    cx + t_bar_w/2, t_top + t_bar_h], fill=TEAL)
    draw.rectangle([cx - t_stem_w/2, t_top + t_bar_h,
                    cx + t_stem_w/2, t_top + t_bar_h + t_stem_h], fill=TEAL)

    # Coral accent dot (OneBeat brand dot)
    dr  = int(s * 0.065)
    dcx = int(cx + t_stem_w/2 + dr * 0.5)
    dcy = int(t_top + t_bar_h + t_stem_h - dr * 0.1)
    draw.ellipse([dcx - dr, dcy - dr, dcx + dr, dcy + dr], fill=CORAL)

    return img

master = make_icon(1024)
for px in [16, 32, 64, 128, 256, 512, 1024]:
    master.resize((px, px), Image.LANCZOS).save(f"{ICONSET}/icon_{px}x{px}.png")
    if px <= 512:
        master.resize((px*2, px*2), Image.LANCZOS).save(f"{ICONSET}/icon_{px}x{px}@2x.png")

print("Icon PNGs written to:", ICONSET)
PYEOF

# Compile iconset → .icns
ICONSET_PARENT="$(dirname "$ICONSET_DIR")"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH" \
    || fail "iconutil failed — cannot compile icon."
ok "Icon compiled → $ICNS_PATH"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Create Desktop shortcut
# ══════════════════════════════════════════════════════════════════════════════
step "Creating Desktop launcher"

APP_PATH="$HOME/Desktop/TAM App.app"

# Remove stale bundle if present
[ -d "$APP_PATH" ] && rm -rf "$APP_PATH"

# Directory structure
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# Info.plist
cat > "$APP_PATH/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>   <string>launch</string>
  <key>CFBundleIdentifier</key>  <string>com.onebeat.tamapp</string>
  <key>CFBundleName</key>        <string>TAM App</string>
  <key>CFBundleIconFile</key>    <string>TamApp</string>
  <key>CFBundleVersion</key>     <string>1.0</string>
  <key>CFBundlePackageType</key> <string>APPL</string>
  <key>LSUIElement</key>         <false/>
</dict>
</plist>
PLIST_EOF

# Launcher script (uses the user's own $HOME/TamApp)
cat > "$APP_PATH/Contents/MacOS/launch" <<'LAUNCH_EOF'
#!/bin/bash
# Start the Flask server if not running, then focus or open the browser window
PORT=5001
URL="http://localhost:$PORT"

if ! lsof -i :$PORT -sTCP:LISTEN -t &>/dev/null; then
  cd "$HOME/TamApp"
  source .venv/bin/activate 2>/dev/null || true
  nohup gunicorn --config gunicorn.conf.py app:app > /tmp/tamapp.log 2>&1 &
  sleep 2
fi

# Try to raise an existing window in Chrome or Safari; open a new one if none found
osascript << EOF
set targetURL to "$URL"
set raised to false

-- Try Google Chrome
try
  tell application "Google Chrome"
    if it is running then
      set ti to 0
      repeat with w in windows
        set ti to 1
        repeat with t in tabs of w
          if URL of t starts with targetURL then
            set active tab index of w to ti
            set index of w to 1
            activate
            set raised to true
            exit repeat
          end if
          set ti to ti + 1
        end repeat
        if raised then exit repeat
      end repeat
    end if
  end tell
end try

-- Try Safari
if not raised then
  try
    tell application "Safari"
      if it is running then
        repeat with w in windows
          repeat with t in tabs of w
            if URL of t starts with targetURL then
              set current tab of w to t
              set index of w to 1
              activate
              set raised to true
              exit repeat
            end if
          end repeat
          if raised then exit repeat
        end repeat
      end if
    end tell
  end try
end if

-- No existing window found — open in default browser
if not raised then
  do shell script "open " & quoted form of targetURL
end if
EOF
LAUNCH_EOF
chmod +x "$APP_PATH/Contents/MacOS/launch"

# Copy icon
cp "$ICNS_PATH" "$APP_PATH/Contents/Resources/TamApp.icns"

# Fix macOS quarantine / refresh Finder
xattr -cr "$APP_PATH" 2>/dev/null
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister \
    -f "$APP_PATH" 2>/dev/null || true
touch "$APP_PATH"
killall Finder 2>/dev/null || true

ok "TAM App launcher created on your Desktop!"

# ══════════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════════
hr
echo -e "${G}  ╔══════════════════════════════════════════╗${N}"
echo -e "${G}  ║         ✅  Setup Complete!              ║${N}"
echo -e "${G}  ╚══════════════════════════════════════════╝${N}"
echo ""
echo "  TAM App is installed at: $INSTALL_DIR"
echo "  Desktop shortcut:  ~/Desktop/TAM App"
echo ""
echo "  👉  Double-click  'TAM App'  on your Desktop to launch."
echo ""
read -rp "  Launch TAM App now? [Y/n] " -n 1 LAUNCH
echo ""
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
    open "$APP_PATH"
fi
echo ""
echo "  Setup complete. You may close this window."
echo ""
