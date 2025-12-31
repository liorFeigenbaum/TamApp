import os
from flask import Flask, render_template, request, redirect, url_for, session

from werkzeug.utils import secure_filename
from toll_box.logs import start_log

from scripts.config_yaml_validation.config_validator import validate_config_yaml

app = Flask(__name__)

app.secret_key = "change_this_in_real_app"

UPLOAD_FOLDER = "out_put"
ALLOWED_EXTENSIONS = {"yaml", "yml"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
	return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def home():
	return render_template("home.html")


@app.route("/config", methods=["GET", "POST"])
def config():
	if request.method == "POST":
		submitted_config = request.form.getlist()
		print(submitted_config)
	
	# if submitted_config:
	return render_template("config.html")


@app.route("/mapper", methods=["GET", "POST"])
def mapper():
	if request.method == "POST":
		submitted_data = request.form.getlist("data[]")
		print(submitted_data)
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
			filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
			file.save(filepath)
			
			# 🔑 store path in session
			session["uploaded_file"] = filepath
			
			result = validate_config_yaml(filepath)
	
		if not result["ok"]:
			error = result["error"]
		else:
			submitted_data = "Config file is valid ✅"
			if result["tam"]:
				warning = result["warning"]
			if result["skip_calc"]:
				skip_watning = result["skip_calc"]
	
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
	
	# @app.route("/contact", methods=["GET", "POST"])
	# def contact():
	#     if request.method == "POST":
	#         name = request.form["name"]
	#         return f"<h2>Hello, {name}!</h2><p><a href='/contact'>Back</a></p>"
	#     return render_template("contact.html")
	
if __name__ == "__main__":
	start_log()
	app.run(debug=True)  # Enables auto-reload and debug output
