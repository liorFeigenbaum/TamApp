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
			
			# 🔑 store path in session
			session["uploaded_file"] = filepath
			
			result = validate_config_yaml(filepath)
		
		if not result["ok"]:
			error = result["error"]
		else:
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
			# Clean up the uploaded zip after processing
			try:
				os.remove(filepath)
			except OSError:
				pass

	return render_template("data_validation.html", result=result, error=error)


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

if __name__ == "__main__":
	start_log()
	port = int(os.environ.get("PORT", 5001))
	app.run(debug=True, port=port)  # Enables auto-reload and debug output
