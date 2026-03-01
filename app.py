import io
import os
import shutil
import uuid
import datetime

import yaml
from flask import Flask, render_template, request, redirect, url_for, session, send_file, make_response

from werkzeug.utils import secure_filename

from toll_box.jsons import pretty_print_json
from toll_box.logs import start_log
from scripts.config_yaml import creat
from scripts.config_yaml_validation.config_validator import validate_config_yaml

app = Flask(__name__)

app.secret_key = "change_this_in_real_app"

UPLOAD_FOLDER = "out_put"
ALLOWED_EXTENSIONS = {"yaml", "yml"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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
	cleanup_session_dir()
	session.pop("wizard_data", None)
	session.pop("config_yaml", None)
	session.pop("uid", None)
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


# @app.route("/contact", methods=["GET", "POST"])
# def contact():
#     if request.method == "POST":
#         name = request.form["name"]
#         return f"<h2>Hello, {name}!</h2><p><a href='/contact'>Back</a></p>"
#     return render_template("contact.html")

if __name__ == "__main__":
	start_log()
	port = int(os.environ.get("PORT", 5001))
	app.run(debug=True, port=port)  # Enables auto-reload and debug output
