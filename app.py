import os
from typing import List, Dict, Any, Optional
from functools import wraps
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import certifi

# ------------------------- CONFIG & DB SETUP -------------------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")  # set this in your environment
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set")

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
)
# client = MongoClient(
#     MONGO_URI
# )

DB_NAME = "hack_the_big_data"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

def get_db() -> Database:
    return client[DB_NAME]

def get_collection(name: str) -> Collection:
    return get_db()[name]

experiments_col = get_collection("experiments")
forums_col = get_collection("forums_global_chat")
access_col = get_collection("access")

# ------------------------- INITIAL DATA -------------------------

DEFAULT_EXPERIMENTS = [
    {
        "experiment_name": "Experiment 1 - Image Classification",
        "link": "https://example.com/exp1",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 2 - NLP Sentiment",
        "link": "https://example.com/exp2",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 3 - Recommender System",
        "link": "https://example.com/exp3",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 4 - Time Series Forecast",
        "link": "https://example.com/exp4",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 5 - Anomaly Detection",
        "link": "https://example.com/exp5",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 6 - Clustering",
        "link": "https://example.com/exp6",
        "comments": [],
    },
    {
        "experiment_name": "Experiment 7 - Reinforcement Learning",
        "link": "https://example.com/exp7",
        "comments": [],
    },
]


def init_db():
    # Seed experiments if empty
    if experiments_col.count_documents({}) == 0:
        experiments_col.insert_many(DEFAULT_EXPERIMENTS)

    # Seed access pin if empty
    if access_col.count_documents({}) == 0:
        default_pin = "200300"  # you can change later in admin portal
        access_col.insert_one({
            "pin_hash": generate_password_hash(default_pin),
            "created_at": datetime.utcnow()
        })


init_db()

# ------------------------- ADMIN AUTH DECORATOR -------------------------

def is_admin_authenticated() -> bool:
    return session.get("admin_authenticated", False)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_authenticated():
            flash("Please enter access code to continue.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------- ADMIN ROUTES -------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        doc = access_col.find_one({})
        if doc:
            pin_hash = doc.get("pin_hash")
            pin_plain = doc.get("pin")
            valid = False
            if pin_hash:
                valid = check_password_hash(pin_hash, pin)
            elif pin_plain:
                valid = (pin_plain == pin)

            if valid:
                session["admin_authenticated"] = True
                flash("Access granted.", "success")
                next_url = request.args.get("next") or url_for("admin_home")
                return redirect(next_url)
        flash("Invalid access code.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    flash("Logged out from admin.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_home():
    exps = list(experiments_col.find({}))
    forums = list(forums_col.find({}).sort("created_at", -1))
    return render_template("admin_home.html", experiments=exps, forums=forums)


@app.route("/admin/experiment/new", methods=["GET", "POST"])
@admin_required
def admin_experiment_new():
    if request.method == "POST":
        name = request.form.get("experiment_name", "").strip()
        link = request.form.get("link", "").strip()
        if not name or not link:
            flash("Experiment name and link are required.", "danger")
        else:
            experiments_col.insert_one({
                "experiment_name": name,
                "link": link,
                "comments": []
            })
            flash("Experiment created.", "success")
            return redirect(url_for("admin_home"))
    return render_template("admin_experiment_form.html", mode="new")


@app.route("/admin/experiment/<exp_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_experiment_edit(exp_id):
    exp = experiments_col.find_one({"_id": ObjectId(exp_id)})
    if not exp:
        flash("Experiment not found.", "danger")
        return redirect(url_for("admin_home"))

    if request.method == "POST":
        name = request.form.get("experiment_name", "").strip()
        link = request.form.get("link", "").strip()
        if not name or not link:
            flash("Experiment name and link are required.", "danger")
        else:
            experiments_col.update_one(
                {"_id": ObjectId(exp_id)},
                {"$set": {"experiment_name": name, "link": link}}
            )
            flash("Experiment updated.", "success")
            return redirect(url_for("admin_home"))

    return render_template("admin_experiment_form.html", mode="edit", experiment=exp)


@app.route("/admin/experiment/<exp_id>/delete", methods=["POST"])
@admin_required
def admin_experiment_delete(exp_id):
    experiments_col.delete_one({"_id": ObjectId(exp_id)})
    flash("Experiment deleted.", "info")
    return redirect(url_for("admin_home"))


@app.route("/admin/forum/<msg_id>/delete", methods=["POST"])
@admin_required
def admin_forum_delete(msg_id):
    forums_col.delete_one({"_id": ObjectId(msg_id)})
    flash("Forum message deleted.", "info")
    return redirect(url_for("admin_home"))


@app.route("/admin/access", methods=["GET", "POST"])
@admin_required
def admin_access():
    current_doc = access_col.find_one({})
    if request.method == "POST":
        new_pin = request.form.get("new_pin", "").strip()
        if len(new_pin) != 6 or not new_pin.isdigit():
            flash("PIN must be a 6-digit number.", "danger")
        else:
            pin_hash = generate_password_hash(new_pin)
            if current_doc:
                access_col.update_one(
                    {"_id": current_doc["_id"]},
                    {"$set": {"pin_hash": pin_hash, "updated_at": datetime.utcnow()},
                     "$unset": {"pin": ""}}
                )
            else:
                access_col.insert_one({
                    "pin_hash": pin_hash,
                    "created_at": datetime.utcnow()
                })
            flash("Access code updated.", "success")
            return redirect(url_for("admin_home"))

    return render_template("admin_access.html", access_doc=current_doc)

# ------------------------- CLIENT / PUBLIC ROUTES -------------------------

@app.route("/")
def root_redirect():
    return redirect(url_for("client_home"))


@app.route("/client", methods=["GET"])
def client_home():
    # Fetch experiments and sort comments by votes desc
    experiments = list(experiments_col.find({}))
    for exp in experiments:
        comments = exp.get("comments", [])
        comments_sorted = sorted(
            comments,
            key=lambda c: c.get("votes", 0),
            reverse=True
        )
        exp["comments"] = comments_sorted

    # Get latest 20 forum messages
    forum_messages = list(
        forums_col.find({}).sort("created_at", -1).limit(20)
    )
    forum_messages.reverse()  # oldest on top

    return render_template(
        "client_home.html",
        experiments=experiments,
        forum_messages=forum_messages
    )


@app.route("/client/experiment/<exp_id>", methods=["GET"])
def client_experiment_detail(exp_id):
    exp = experiments_col.find_one({"_id": ObjectId(exp_id)})
    if not exp:
        flash("Experiment not found.", "danger")
        return redirect(url_for("client_home"))
    comments = exp.get("comments", [])
    comments_sorted = sorted(comments, key=lambda c: c.get("votes", 0), reverse=True)
    exp["comments"] = comments_sorted
    return render_template("client_experiment_detail.html", experiment=exp)


@app.route("/client/experiment/<exp_id>/comment", methods=["POST"])
def client_add_comment(exp_id):
    name = request.form.get("name", "").strip()
    text = request.form.get("comment", "").strip()

    if not text:
        flash("Comment cannot be empty.", "danger")
        return redirect(request.referrer or url_for("client_home"))

    if not name:
        name = "Anonymous"

    comment_doc = {
        "_id": ObjectId(),  # for voting
        "name": name,
        "text": text,
        "votes": 0,
        "created_at": datetime.utcnow()
    }

    experiments_col.update_one(
        {"_id": ObjectId(exp_id)},
        {"$push": {"comments": comment_doc}}
    )

    flash("Comment added.", "success")
    return redirect(request.referrer or url_for("client_home"))


@app.route("/client/experiment/<exp_id>/comment/<comment_id>/vote", methods=["POST"])
def client_vote_comment(exp_id, comment_id):
    # Increase vote count for specific comment in experiment
    experiments_col.update_one(
        {"_id": ObjectId(exp_id), "comments._id": ObjectId(comment_id)},
        {"$inc": {"comments.$.votes": 1}}
    )
    return redirect(request.referrer or url_for("client_home"))


@app.route("/client/forum/post", methods=["POST"])
def client_forum_post():
    name = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()

    if not message:
        flash("Message cannot be empty.", "danger")
        return redirect(request.referrer or url_for("client_home"))

    if not name:
        name = "Anonymous"

    forums_col.insert_one({
        "name": name,
        "message": message,
        "created_at": datetime.utcnow()
    })
    flash("Message posted to global chat.", "success")
    return redirect(request.referrer or url_for("client_home"))


if __name__ == "__main__":
    # For local testing
    app.run(debug=True)
