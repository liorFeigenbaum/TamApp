from flask import Flask, render_template, request

from toll_box.logs import start_log

app = Flask(__name__)


@app.route("/")
def home():
	return render_template("home.html")


@app.route("/config", methods=["GET", "POST"])
def config():
	return render_template("config.html")


@app.route("/mapper", methods=["GET", "POST"])
def mapper():
	if request.method == "POST":
		submitted_data = request.form.getlist("data[]")
		print(submitted_data)
		return render_template("mapper.html", submitted_data=submitted_data)
	return render_template("mapper.html", submitted_data=None)


# @app.route("/contact", methods=["GET", "POST"])
# def contact():
#     if request.method == "POST":
#         name = request.form["name"]
#         return f"<h2>Hello, {name}!</h2><p><a href='/contact'>Back</a></p>"
#     return render_template("contact.html")

if __name__ == "__main__":
	app.run(debug=True)  # Enables auto-reload and debug output
