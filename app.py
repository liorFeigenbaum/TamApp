import io
import os
import re
import shutil
import signal
import subprocess
import threading
import uuid
import datetime

import yaml
from flask import Flask, render_template, request, redirect, url_for, session, send_file, make_response, jsonify

from werkzeug.utils import secure_filename

from toll_box.jsons import pretty_print_json
from toll_box.logs import start_log
from scripts.config_yaml import creat
from scripts.config_yaml_validation.config_validator import validate_config_yaml
from scripts.data_validation.validator import validate_zip
from scripts.data_extractor import backup_io as backup_io_script
from scripts.data_validation import pdf_report as validation_pdf

app = Flask(__name__)

app.secret_key = "change_this_in_real_app"

UPLOAD_FOLDER = "out_put"
ALLOWED_EXTENSIONS = {"yaml", "yml"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Root of the git repository (same directory as this file)
_REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Startup: wipe all leftover per-session directories from previous runs ──
_UUID_RE = re.compile(r'^[0-9a-f]{32}$')
for _item in os.listdir(UPLOAD_FOLDER):
	_item_path = os.path.join(UPLOAD_FOLDER, _item)
	if os.path.isdir(_item_path) and _UUID_RE.match(_item):
		shutil.rmtree(_item_path, ignore_errors=True)


def get_session_dir():
	"""Return (and create) a per-session subdirectory under out_put/."""
	if 'uid' not in session:
		session['uid'] = uuid.uuid4().hex
	path = os.path.join(UPLOAD_FOLDER, session['uid'])
	os.makedirs(path, exist_ok=True)
	return path


def cleanup_session_dir():
	"""Remove the per-session directory if it exists."""
	uid = session.get('uid')
	if uid:
		path = os.path.join(UPLOAD_FOLDER, uid)
		shutil.rmtree(path, ignore_errors=True)


class IndentDumper(yaml.SafeDumper):
	def increase_indent(self, flow=False, indentless=False):
		return super().increase_indent(flow, False)


def allowed_file(filename):
	return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def home():
	# Clean this session's files
	cleanup_session_dir()
	session.pop("wizard_data", None)
	session.pop("config_yaml", None)
	session.pop("uploaded_file", None)
	session.pop("uid", None)

	# Also purge any orphaned session directories left by other/previous sessions
	for _item in os.listdir(UPLOAD_FOLDER):
		_item_path = os.path.join(UPLOAD_FOLDER, _item)
		if os.path.isdir(_item_path) and _UUID_RE.match(_item):
			shutil.rmtree(_item_path, ignore_errors=True)

	return render_template("home.html")


@app.route("/config", methods=["GET", "POST"])
def config():
	if request.method == "POST":
		submitted_config = request.form.to_dict(flat=False)
		
		config_dict = creat.main(submitted_config)
		
		yaml_config = yaml.dump(
			config_dict,
			Dumper=IndentDumper,
			sort_keys=False,
			default_flow_style=False,
			indent=2,
			allow_unicode=True,
		)
		
		session["config_yaml"] = yaml_config
		session["wizard_data"] = submitted_config
		
		return redirect(url_for("preview"))
	# if submitted_config:
	existing_data = session.get("wizard_data", {})
	return render_template("config.html", data=existing_data)


@app.route("/preview")
def preview():
	wizard_data = session.get("wizard_data")
	if not wizard_data:
		return redirect(url_for("config"))
	
	# Rebuild YAML from saved wizard data
	config_dict = creat.main(wizard_data)

	yaml_text = yaml.dump(
			config_dict,
			Dumper=IndentDumper,
			sort_keys=False,
			default_flow_style=False,
			indent=2,
			allow_unicode=True,
	)

	# (Optional) keep it in session if download uses it directly
	session["config_yaml"] = yaml_text
	
	return render_template("preview.html", yaml_text=yaml_text)


@app.route("/mapper", methods=["GET", "POST"])
def mapper():
	if request.method == "POST":
		submitted_data = request.form.getlist("data[]")
		return render_template("mapper.html", submitted_data=submitted_data)
	return render_template("mapper.html", submitted_data=None)


@app.route("/configV", methods=["GET", "POST"])
def config_validator():
	submitted_data = None
	error = None
	warning = None
	skip_watning = None
	
	if request.method == "POST":
		file = request.files.get("file")
		
		if not file or file.filename == "":
			error = "No file uploaded"
		
		elif not allowed_file(file.filename):
			error = "Only .yaml / .yml files are allowed"
		
		else:
			filename = secure_filename(file.filename)
			filepath = os.path.join(get_session_dir(), filename)
			file.save(filepath)

			result = validate_config_yaml(filepath)

			if not result["ok"]:
				# Validation failed — delete the file and do NOT store it in session
				os.remove(filepath)
				error = result["error"]
			else:
				# 🔑 only store path in session when the config is valid
				session["uploaded_file"] = filepath
				submitted_data = "Config file is valid ✅"
				if result.get("tam"):
					warning = result.get("warning")
				if result.get("skip_calc"):
					skip_watning = result.get("skip_calc")
	
	return render_template(
		"configV.html",
		submitted_data=submitted_data,
		error=error,
		warning=warning,
		skip_watning=skip_watning
		)


@app.route("/back", methods=["POST"])
def back():
	filepath = session.pop("uploaded_file", None)
	
	if filepath and os.path.exists(filepath):
		os.remove(filepath)
	
	return redirect(url_for("home"))


@app.route("/download")
def download():
	yaml_text = session.get("config_yaml")
	if not yaml_text:
		return redirect(url_for("home"))
	
	# 🔹 Create a Flask response for file download
	response = make_response(yaml_text)
	response.headers["Content-Disposition"] = "attachment; filename=config.yaml"
	response.headers["Content-Type"] = "text/yaml"

	# 🔹 Clear wizard session after download
	session.pop("config_yaml", None)
	session.pop("wizard_data", None)
	
	return response


def _check_aws_sso():
	"""Return (ok, issue_type, issue_message) for the aws sso login --profile prod prerequisite."""
	aws_bin = "/opt/homebrew/bin/aws"
	if not os.path.isfile(aws_bin):
		return False, "no_cli", f"AWS CLI not found at {aws_bin}"
	aws_config = os.path.expanduser("~/.aws/config")
	if not os.path.isfile(aws_config):
		return False, "no_profile", "~/.aws/config not found"
	with open(aws_config) as f:
		if "[profile prod]" not in f.read():
			return False, "no_profile", "'prod' SSO profile not found in ~/.aws/config"
	# Verify the session is actually active
	result = subprocess.run(
		[aws_bin, "sts", "get-caller-identity", "--profile", "prod"],
		capture_output=True, text=True, timeout=10
	)
	if result.returncode != 0:
		return False, "expired", "SSO session expired or not logged in"
	return True, None, None


@app.route("/data_extractor")
def data_extractor():
	aws_ok, aws_issue_type, aws_issue = _check_aws_sso()
	return render_template("data_extractor.html", aws_ok=aws_ok, aws_issue_type=aws_issue_type, aws_issue=aws_issue)


@app.route("/data_extractor/backup-io", methods=["GET", "POST"])
def backup_io():
	results    = None
	error      = None
	prev_start = None
	prev_end   = None

	if request.method == "POST":
		config_file = request.files.get("config_file")
		start_str   = request.form.get("start_date", "").strip()
		end_str     = request.form.get("end_date",   "").strip()
		output_dir  = request.form.get("output_dir", "~/Desktop/backup_io").strip()

		prev_start = start_str
		prev_end   = end_str

		if not config_file or config_file.filename == "":
			error = "Please upload a config.yaml file."
		elif not start_str or not end_str:
			error = "Please select a date range."
		else:
			try:
				start_date = datetime.date.fromisoformat(start_str)
				end_date   = datetime.date.fromisoformat(end_str)

				sdir     = get_session_dir()
				filename = secure_filename(config_file.filename)
				cfg_path = os.path.join(sdir, filename)
				config_file.save(cfg_path)

				results, error = backup_io_script.run(
					cfg_path, start_date, end_date, output_dir
				)
			except Exception as e:
				error = str(e)

	return render_template(
		"backup_io.html",
		results=results,
		error=error,
		prev_start=prev_start,
		prev_end=prev_end,
	)


@app.route("/api/browse-dir")
def browse_dir():
	"""Return subdirectories of the requested path for the directory picker modal."""
	raw = request.args.get("path", "~").strip() or "~"
	path = os.path.expanduser(raw)
	path = os.path.abspath(path)

	if not os.path.isdir(path):
		return jsonify({"error": f"Not a directory: {path}"}), 400

	parent = os.path.dirname(path) if path != os.path.sep else None

	try:
		entries = sorted(
			e for e in os.listdir(path)
			if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")
		)
	except PermissionError:
		entries = []

	return jsonify({"current": path, "parent": parent, "dirs": entries})


@app.route("/api/create-dir", methods=["POST"])
def create_dir():
	"""Create a new subdirectory inside the given parent path."""
	data   = request.get_json(silent=True) or {}
	parent = data.get("parent", "").strip()
	name   = data.get("name", "").strip()

	if not parent or not name:
		return jsonify({"error": "parent and name are required"}), 400

	# Reject path traversal attempts
	if "/" in name or "\\" in name or name in (".", ".."):
		return jsonify({"error": "Invalid folder name"}), 400

	parent = os.path.abspath(os.path.expanduser(parent))
	if not os.path.isdir(parent):
		return jsonify({"error": f"Parent is not a directory: {parent}"}), 400

	new_path = os.path.join(parent, name)
	try:
		os.makedirs(new_path, exist_ok=True)
	except Exception as e:
		return jsonify({"error": str(e)}), 500

	return jsonify({"created": new_path})


def _serialisable_result(result: dict) -> dict:
	"""Return a copy of a validate_zip result safe to store in the Flask session.
	Removes any non-serialisable values (pandas DataFrames kept under '_df')."""
	import copy
	clean = copy.deepcopy(result)
	for file_info in clean.get("files", {}).values():
		file_info.pop("_df", None)
	return clean


@app.route("/data_validate", methods=["GET", "POST"])
def data_validate():
	result = None
	error  = None

	if request.method == "POST":
		file = request.files.get("file")

		if not file or file.filename == "":
			error = "No file uploaded."
		elif not file.filename.lower().endswith(".zip"):
			error = "Please upload a .zip file."
		else:
			sdir = get_session_dir()
			filename = secure_filename(file.filename)
			filepath = os.path.join(sdir, filename)
			file.save(filepath)
			result = validate_zip(filepath, session_dir=sdir)
			# Store serialisable snapshot so the PDF route can use it
			session["last_validation_result"] = _serialisable_result(result)
			session["last_validation_zip"]    = filename
			# Clean up the uploaded zip after processing
			try:
				os.remove(filepath)
			except OSError:
				pass

	return render_template("data_validation.html", result=result, error=error)


@app.route("/data_validate/export_pdf")
def data_validate_export_pdf():
	"""Generate and return a PDF summary of the last validation run."""
	result = session.get("last_validation_result")
	if not result:
		return "No validation result found. Please run a validation first.", 404

	zip_name = session.get("last_validation_zip", "unknown.zip")
	pdf_bytes = validation_pdf.build(result, zip_name)

	response = make_response(pdf_bytes)
	response.headers["Content-Type"] = "application/pdf"
	response.headers["Content-Disposition"] = (
		f'attachment; filename="validation_report_{datetime.date.today()}.pdf"'
	)
	return response


@app.route("/download_validation_file/<filename>")
def download_validation_file(filename):
	"""Serve a validation artefact (e.g. duplicates CSV) from the session directory."""
	safe_name = secure_filename(filename)
	filepath = os.path.join(get_session_dir(), safe_name)
	if not os.path.exists(filepath):
		return "File not found or session expired.", 404
	return send_file(filepath, as_attachment=True, download_name=safe_name)


# @app.route("/contact", methods=["GET", "POST"])
# def contact():
#     if request.method == "POST":
#         name = request.form["name"]
#         return f"<h2>Hello, {name}!</h2><p><a href='/contact'>Back</a></p>"
#     return render_template("contact.html")


# ── Git update routes ────────────────────────────────────────────────────────

@app.route("/git_check")
def git_check():
	"""Return whether the remote has commits not yet in HEAD."""
	try:
		# Silently fetch (no output); ignore errors (e.g. no network)
		subprocess.run(
			["git", "fetch", "--quiet"],
			cwd=_REPO_DIR, capture_output=True, timeout=10
		)
		result = subprocess.run(
			["git", "rev-list", "--count", "HEAD..@{u}"],
			cwd=_REPO_DIR, capture_output=True, text=True, timeout=5
		)
		count = int(result.stdout.strip() or "0")
		return jsonify(has_updates=count > 0, count=count)
	except Exception as e:
		return jsonify(has_updates=False, count=0, error=str(e))


def _reload_gunicorn_after(delay: float = 0.8):
	"""Send SIGHUP to the gunicorn master so it gracefully reloads workers."""
	def _do():
		import time
		time.sleep(delay)
		port = int(os.environ.get("PORT", 5001))
		try:
			# Workers are listening on the port; the master is their parent
			r = subprocess.run(
				["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
				capture_output=True, text=True
			)
			worker_pids = [int(p) for p in r.stdout.split() if p.strip().isdigit()]
			seen_masters = set()
			for wpid in worker_pids:
				pr = subprocess.run(
					["ps", "-o", "ppid=", "-p", str(wpid)],
					capture_output=True, text=True
				)
				ppid_str = pr.stdout.strip()
				if ppid_str.isdigit():
					master = int(ppid_str)
					if master not in seen_masters:
						seen_masters.add(master)
						os.kill(master, signal.SIGHUP)
		except Exception:
			# Fallback: broadcast SIGHUP to any gunicorn process in this tree
			subprocess.run(["pkill", "-HUP", "-f", "gunicorn"], capture_output=True)
	threading.Thread(target=_do, daemon=True).start()


@app.route("/git_update", methods=["POST"])
def git_update():
	"""Pull latest commits then gracefully reload gunicorn workers."""
	try:
		result = subprocess.run(
			["git", "pull", "--ff-only"],
			cwd=_REPO_DIR, capture_output=True, text=True, timeout=60
		)
		if result.returncode != 0:
			return jsonify(ok=False, error=result.stderr.strip()), 500

		_reload_gunicorn_after(delay=0.6)
		return jsonify(ok=True, output=result.stdout.strip())
	except Exception as e:
		return jsonify(ok=False, error=str(e)), 500

@app.route("/create_launcher", methods=["POST"])
def create_launcher():
	"""Generate a TAM App.app bundle on the user's Desktop with correct paths."""
	import platform, tempfile, stat
	if platform.system() != "Darwin":
		return jsonify(ok=False, error="Desktop launcher is only supported on macOS."), 400

	home     = os.path.expanduser("~")
	app_dir  = _REPO_DIR
	port     = int(os.environ.get("PORT", 5001))
	app_path = os.path.join(home, "Desktop", "TAM App.app")

	try:
		# ── 1. Build directory structure ────────────────────────────────────
		if os.path.exists(app_path):
			shutil.rmtree(app_path)
		os.makedirs(os.path.join(app_path, "Contents", "MacOS"),     exist_ok=True)
		os.makedirs(os.path.join(app_path, "Contents", "Resources"), exist_ok=True)

		# ── 2. Info.plist ───────────────────────────────────────────────────
		plist = """\
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
</plist>"""
		with open(os.path.join(app_path, "Contents", "Info.plist"), "w") as f:
			f.write(plist)

		# ── 3. Generate .icns icon ───────────────────────────────────────────
		try:
			from PIL import Image, ImageDraw
			BG_CARD = (26,  42,  58)
			TEAL    = (31, 108, 109)
			CORAL   = (253, 96,  74)
			BORDER  = (31,  50,  72)

			def _make_icon(size):
				img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
				draw = ImageDraw.Draw(img)
				s, pad, r = size, size * 0.04, int(size * 0.18)
				draw.rounded_rectangle([pad, pad, s-pad, s-pad], radius=r,
				                       fill=BG_CARD, outline=BORDER, width=max(2, int(s*0.012)))
				bar_h = int(s * 0.045)
				draw.rounded_rectangle([pad, pad, s-pad, pad+bar_h], radius=r, fill=TEAL)
				draw.rectangle([pad, pad+bar_h//2, s-pad, pad+bar_h], fill=BG_CARD)
				cx, cy = s/2, s/2
				t_bar_w, t_bar_h  = s*0.60, s*0.13
				t_stem_w, t_stem_h = s*0.19, s*0.36
				t_top = cy - (t_bar_h + t_stem_h)/2 - s*0.02
				draw.rectangle([cx-t_bar_w/2, t_top, cx+t_bar_w/2, t_top+t_bar_h], fill=TEAL)
				draw.rectangle([cx-t_stem_w/2, t_top+t_bar_h, cx+t_stem_w/2, t_top+t_bar_h+t_stem_h], fill=TEAL)
				dr  = int(s * 0.065)
				dcx = int(cx + t_stem_w/2 + dr*0.5)
				dcy = int(t_top + t_bar_h + t_stem_h - dr*0.1)
				draw.ellipse([dcx-dr, dcy-dr, dcx+dr, dcy+dr], fill=CORAL)
				return img

			with tempfile.TemporaryDirectory() as tmpdir:
				iconset = os.path.join(tmpdir, "TamApp.iconset")
				icns    = os.path.join(tmpdir, "TamApp.icns")
				os.makedirs(iconset)
				master = _make_icon(1024)
				for px in [16, 32, 64, 128, 256, 512, 1024]:
					master.resize((px, px), Image.LANCZOS).save(f"{iconset}/icon_{px}x{px}.png")
					if px <= 512:
						master.resize((px*2, px*2), Image.LANCZOS).save(f"{iconset}/icon_{px}x{px}@2x.png")
				subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
				shutil.copy(icns, os.path.join(app_path, "Contents", "Resources", "TamApp.icns"))
		except Exception:
			pass  # Icon is nice-to-have; don't fail the whole operation

		# ── 4. Launcher shell script ────────────────────────────────────────
		launch_script = f"""\
#!/bin/bash
# TAM App launcher — generated by the app for this machine
exec > /tmp/tamapp_launcher.log 2>&1

PORT={port}
URL="http://localhost:$PORT"
APP_DIR="{app_dir}"

export PATH="$APP_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if ! /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t &>/dev/null; then
  cd "$APP_DIR"
  source .venv/bin/activate 2>/dev/null || true
  nohup gunicorn --config gunicorn.conf.py app:app >> /tmp/tamapp.log 2>&1 &
  i=0
  while [ $i -lt 15 ]; do
    sleep 1
    /usr/sbin/lsof -i :$PORT -sTCP:LISTEN -t &>/dev/null && break
    i=$((i+1))
  done
fi

/usr/bin/osascript << EOF
set targetURL to "$URL"
set raised to false
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
if not raised then
  do shell script "/usr/bin/open '$URL'"
end if
EOF
"""
		launch_path = os.path.join(app_path, "Contents", "MacOS", "launch")
		with open(launch_path, "w") as f:
			f.write(launch_script)
		os.chmod(launch_path, os.stat(launch_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

		# ── 5. Clear quarantine & refresh Finder ────────────────────────────
		subprocess.run(["xattr", "-cr", app_path], capture_output=True)
		subprocess.run([
			"/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/"
			"LaunchServices.framework/Versions/A/Support/lsregister",
			"-f", app_path
		], capture_output=True)
		subprocess.run(["touch", app_path], capture_output=True)
		subprocess.run(["killall", "Finder"], capture_output=True)

		return jsonify(ok=True)

	except Exception as e:
		return jsonify(ok=False, error=str(e)), 500


if __name__ == "__main__":
	start_log()
	port = int(os.environ.get("PORT", 5001))
	app.run(debug=True, port=port)  # Enables auto-reload and debug output
