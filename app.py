from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)
load_dotenv()

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("database")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = os.getenv("modification")
app.config["SECRET_KEY"] = os.getenv("secret_key")
app.config["JWT_SECRET_KEY"] = os.getenv("jwt_key")
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.json.sort_keys = False

db = SQLAlchemy(app)
jwt = JWTManager(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(90), nullable=False)
    email = db.Column(db.String(90), unique=True, nullable=False)
    password_hash = db.Column(db.String(90), nullable=False)
    expenses = db.relationship("Expense", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.now())
    description = db.Column(db.String(90), nullable=False)
    amount = db.Column(db.String(90), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    expenses = db.relationship("Expense", backref="category", lazy=True)

with app.app_context():
    db.create_all()

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or "name" not in data or "email" not in data or "password" not in data:
        raise ValueError("name, email and password required")
    user = User(name=data["name"], email=data["email"])
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=user.id)
    return jsonify({"token": token}), 200

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or "email" not in data or "password" not in data:
        raise ValueError("email and password required")
    user = User.query.filter_by(email=data["email"]).first()
    token = create_access_token(identity=user.id)

    if user and user.check_password(data["password"]):
        return jsonify({"token": token})
    else:
        return jsonify("email or password is invalid")

@app.route("/expense", methods=["POST"])
@jwt_required()
def add():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data or "description" not in data or "amount" not in data or "category" not in data:
        raise ValueError("description, amount, category required")
    expense = Expense(description=data["description"], amount=data["amount"], user_id=user_id)
    category = Category.query.filter_by(name=data["category"]).first()
    if not category:
        category = Category(name=data["category"])
        db.session.add(category)
        db.session.commit()
    expense.category_id = category.id
    db.session.add(expense)
    db.session.commit()

    return jsonify({
        "id": expense.id,
        "date": expense.date,
        "description": expense.description,
        "amount": expense.amount,
        "category": category.name
    }), 200
    
@app.route("/expense/<int:id>", methods=["PUT"])
@jwt_required()
def update(id):
    user_id = get_jwt_identity()
    expense = Expense.query.get(id)

    if not expense:
        return jsonify({"message": "Expense not found"})
    
    if expense.user_id != user_id:
        return jsonify({"message": "Forbbiden"})

    data = request.get_json()
    if not data or "description" not in data or "amount" not in data:
        raise ValueError("description and amount required")
    expense.description = data["description"]
    expense.amount = data["amount"]
    db.session.commit()
    return jsonify({
        "id": expense.id,
        "date": expense.date,
        "description": expense.description,
        "amount": expense.amount,
        "category": expense.category.name
    }), 200

@app.route("/expenses/<int:id>", methods=["DELETE"])
@jwt_required()
def delete(id):
    user_id = get_jwt_identity()
    expense = Expense.query.get(id)
    
    if not expense:
        return jsonify({"message": "Expense not found"})
    
    if expense.user_id != user_id:
        return jsonify({"message": "Forbidden"}), 403
    
    db.session.delete(expense)
    db.session.commit()
    return jsonify("success"), 204

@app.route("/expense", methods=["GET"])
@jwt_required()
def get_all():
    expense = Expense.query.all()

    if not expense:
        return jsonify({"message": "Expense not found"})
    
    return jsonify([
        {
            "ID": i.id,
            "Date": i.date,
            "Description": i.description,
            "Amount": i.amount,
            "category": i.category.name
        }
        for i in expense
    ]), 200

@app.route("/expenses", methods=["POST"])
@jwt_required()
def custom_date():
    expense = Expense.query.all()
    df = pd.DataFrame([{
        "id": i.id,
        "date": i.date,
        "description": i.description,
        "amount": i.amount,
        "category": i.category.name
    }for i in expense])
    data = request.get_json()
    if not data or "start" not in data or "end" not in data:
        raise ValueError("Start and end required")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    filter = df.loc[(df["date"] >= data["start"])
                    & (df["date"] <= data["end"])]
    return jsonify(filter.to_dict(orient="records")), 200

@app.route("/expense/week", methods=["GET"])
@jwt_required()
def past_week():
    expense = Expense.query.all()
    if not expense:
        return jsonify({"message": "expense not found"})
    
    df = pd.DataFrame([{
        "id": i.id,
        "date": i.date,
        "descsription": i.description,
        "amount": i.amount,
        "category": i.category.name
    }for i in expense])

    today = datetime.today().date()
    start_of_this_week = today - timedelta(days=today.weekday())
    prev_week_start = start_of_this_week - timedelta(weeks=1)
    prev_week_end = start_of_this_week - timedelta(days=1)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    filter = df.loc[(df["date"] >= prev_week_start) 
                    & (df["date"] <= prev_week_end)]
    if filter.empty:
        return jsonify({"message": "expense past week not found"})
    
    return jsonify(filter.to_dict(orient="records")), 200

@app.route("/expense/month", methods=["GET"])
@jwt_required()
def past_month():
    expense = Expense.query.all()
    if not expense:
        return jsonify({"message": "expense not found"})
    
    df = pd.DataFrame([{
        "id": i.id,
        "date": i.date,
        "description": i.description,
        "amount": i.amount,
        "category": i.category.name
    }for i in expense])
    today = datetime.today().date()
    prev_month_start = (today - timedelta(days=today.day)).replace(day=1)
    prev_month_end = today - timedelta(days=today.day)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    filter = df.loc[(df["date"] >= prev_month_start)
                    & (df["date"] <= prev_month_end)]
    if filter.empty:
        return jsonify({'message': "expense past month not found"})
    
    return jsonify(filter.to_dict(orient="records")), 200

@app.route("/expense/last-3-month", methods=["GET"])
@jwt_required()
def last_3_month():
    expense = Expense.query.all()
    df = pd.DataFrame([{
        "id": i.id,
        "date": i.date,
        "description": i.description,
        "amount": i.amount,
        "category": i.category.name
    } for i in expense])
    today = datetime.today().date()
    prev_month_start = (today - timedelta(weeks=12)).replace(day=1)
    prev_month_end = today - timedelta(days=today.day)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    filter = df.loc[(df["date"] >= prev_month_start)
                    & (df["date"] <= prev_month_end)]
    
    if filter.empty:
        return jsonify({"message": "expense last 3 month not found"})
    
    return jsonify(filter.to_dict(orient="records")), 200
    
@app.route("/expense/total", methods=["GET"])
@jwt_required()
def total():
    expense = Expense.query.all()
    total = 0
    for i in expense:
        total += int(i.amount.replace("$", ""))
    return jsonify({"total": f"${total}"})

@app.route("/expense/total/<int:id>", methods=["GET"])
@jwt_required()
def total_by_month(id):
    expense = Expense.query.all()
    total = 0
    month = ""
    for i in expense:
        date = pd.to_datetime(i.date, format="%Y-%m-%d")
        if date.month == id:
            total += int(i.amount.replace("$", ""))
            month += date.strftime("%B")
    return jsonify(f"Total expense for {"".join(dict.fromkeys(month))}: ${total}")


if __name__ == "__main__":
    app.run(debug=True)