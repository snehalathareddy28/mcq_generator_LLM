from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import io
import re
import json
import random
from datetime import datetime
from fpdf import FPDF
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mcq.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    tests = db.relationship('Test', backref='author', lazy=True)
    attempts = db.relationship('Attempt', backref='user', lazy=True)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('Question', backref='test', lazy=True, cascade="all, delete")
    attempts = db.relationship('Attempt', backref='test', lazy=True, cascade="all, delete")

    main_heading = db.Column(db.String(200), nullable=True)

    @property
    def display_heading(self):
        return self.main_heading if self.main_heading else (self.topic.split(',')[0].strip() if ',' in self.topic else self.topic)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.String(200), nullable=False)

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    max_score = db.Column(db.Integer, nullable=False)
    taken_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create tables
with app.app_context():
    db.create_all()
    # Migration to add main_heading
    import sqlite3
    import os
    db_path = os.path.join(app.instance_path, 'mcq.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.execute('ALTER TABLE test ADD COLUMN main_heading VARCHAR(200);')
            conn.commit()
            conn.close()
        except Exception:
            pass # Column likely already exists

# Load model (Global)
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
model_name = "google/flan-t5-base"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device)

# Auth Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Use pbkdf2:sha256 as standard for werkzeug security
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
            
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def generate_and_save_test(topic, difficulty, num_q, user_id, main_heading=""):
    # Parse multiple topics
    topics_list = [t.strip() for t in topic.split(',') if t.strip()]
    if not topics_list:
        topics_list = [topic]

    # Create new Test entry (save the original input string as the topic)
    new_test = Test(user_id=user_id, topic=topic, difficulty=difficulty, main_heading=main_heading)
    db.session.add(new_test)
    db.session.commit()

    # Batch Step 1: Generate all unique questions
    unique_questions = []
    attempts = 0
    max_attempts = num_q * 5 # Safety limit to prevent infinite loops

    while len(unique_questions) < num_q and attempts < max_attempts:
        needed = num_q - len(unique_questions)
        # Batch generate 'needed' amount of questions
        q_prompts = []
        for i in range(needed):
            t = topics_list[(len(unique_questions) + i) % len(topics_list)]
            q_prompts.append(f"Write a completely unique and different question about {t} ({difficulty} difficulty).")
            
        q_inputs = tokenizer(q_prompts, return_tensors="pt", padding=True).to(device)
        q_outputs = model.generate(**q_inputs, max_new_tokens=50, do_sample=True, temperature=0.95 + (attempts * 0.05))
        batch_texts = [tokenizer.decode(out, skip_special_tokens=True).strip() for out in q_outputs]
        
        for text in batch_texts:
            # Basic cleanup and duplicate check
            clean_text = text.replace("Question:", "").strip()
            if clean_text and clean_text not in unique_questions:
                unique_questions.append(clean_text)
            if len(unique_questions) >= num_q:
                break
        attempts += 1
        
    questions_text = unique_questions
    # Update num_q in case we hit the max_attempts and couldn't find enough unique ones
    num_q = len(questions_text)

    # Batch Step 2: Generate Correct Answers for all
    c_prompts = [f"What is the correct answer to: '{q}'" for q in questions_text]
    c_inputs = tokenizer(c_prompts, return_tensors="pt", padding=True).to(device)
    c_outputs = model.generate(**c_inputs, max_new_tokens=30, do_sample=True, temperature=0.7)
    correct_answers = [tokenizer.decode(out, skip_special_tokens=True).strip() for out in c_outputs]

    # Batch Step 3: Generate Incorrect Answers for all
    wrong_answers_list = [[] for _ in range(num_q)]
    for j in range(3):
        w_prompts = []
        for idx, q in enumerate(questions_text):
            existing = wrong_answers_list[idx]
            if existing:
                prompt = f"Write an incorrect answer to: '{q}'. It must be different from: {', '.join(existing)}"
            else:
                prompt = f"Write a completely incorrect but plausible answer to: '{q}'"
            w_prompts.append(prompt)
            
        w_inputs = tokenizer(w_prompts, return_tensors="pt", padding=True).to(device)
        w_outputs = model.generate(**w_inputs, max_new_tokens=30, do_sample=True, temperature=0.95)
        w_texts = [tokenizer.decode(out, skip_special_tokens=True).strip() for out in w_outputs]
        
        for idx, w_text in enumerate(w_texts):
            ans = w_text if len(w_text) > 0 else f"Incorrect Option {j+1}"
            
            # Deduplication fallback
            if ans in wrong_answers_list[idx] or ans == correct_answers[idx]:
                fallbacks = ["None of the above", "All of the above", "Not applicable"]
                ans = fallbacks[j] if j < len(fallbacks) else f"Option {j+1}"
                
            wrong_answers_list[idx].append(ans)

    # Assemble the questions and save to DB
    for i in range(num_q):
        options_found = [correct_answers[i]] + wrong_answers_list[i]
        random.shuffle(options_found)
            
        new_question = Question(
            test_id=new_test.id,
            question_text=questions_text[i],
            option_a=options_found[0],
            option_b=options_found[1],
            option_c=options_found[2],
            option_d=options_found[3],
            correct_answer=correct_answers[i]
        )
        db.session.add(new_question)
    
    db.session.commit()
    return new_test.id

@app.route("/")
@login_required
def home():
    # GET request: show dashboard and recent tests
    user_tests = Test.query.filter_by(user_id=current_user.id).order_by(Test.created_at.desc()).limit(5).all()
    return render_template("index.html", user_tests=user_tests)

@app.route("/generate/<gen_type>", methods=["GET", "POST"])
@login_required
def generate(gen_type):
    if gen_type not in ["pdf", "test"]:
        flash("Invalid generation type.", "danger")
        return redirect(url_for("home"))
        
    if request.method == "POST":
        main_heading = request.form.get("main_heading", "").strip()
        topic = request.form.get("topic", "")
        difficulty = request.form.get("difficulty", "Medium")
        num_questions = request.form.get("num_questions", "5")
        try:
            num_q = int(num_questions)
        except:
            num_q = 5
            
        test_id = generate_and_save_test(topic, difficulty, num_q, current_user.id, main_heading)
        
        if gen_type == "pdf":
            return redirect(url_for('download_pdf', test_id=test_id))
        else:
            return redirect(url_for('take_test', test_id=test_id))
            
    return render_template("generate.html", gen_type=gen_type)


@app.route("/take_test/<int:test_id>")
@login_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    return render_template("take_test.html", test=test)

@app.route("/submit_test/<int:test_id>", methods=["POST"])
@login_required
def submit_test(test_id):
    test = Test.query.get_or_404(test_id)
    score = 0
    max_score = len(test.questions)
    
    for q in test.questions:
        user_answer = request.form.get(f'q_{q.id}')
        if user_answer == q.correct_answer:
            score += 1
            
    attempt = Attempt(user_id=current_user.id, test_id=test.id, score=score, max_score=max_score)
    db.session.add(attempt)
    db.session.commit()
    
    flash(f'Test completed! You scored {score} out of {max_score}.', 'success')
    return redirect(url_for('history'))

@app.route("/history")
@login_required
def history():
    attempts = Attempt.query.filter_by(user_id=current_user.id).order_by(Attempt.taken_at.desc()).all()
    return render_template("history.html", attempts=attempts)

@app.route("/download_pdf/<int:test_id>")
def download_pdf(test_id):
    test = Test.query.get_or_404(test_id)
    
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"Test: {test.display_heading} ({test.difficulty})", ln=True, align="C")
    pdf.ln(5)
    
    for idx, q in enumerate(test.questions, 1):
        # Question text
        pdf.set_font("Arial", 'B', 12)
        question_text = f"{idx}. {q.question_text}".encode('latin-1', 'replace').decode('latin-1')
        
        # Save current Y
        current_y = pdf.get_y()
        
        # Print the right side brace
        pdf.set_xy(160, current_y)
        pdf.cell(40, 10, "[          ]", 0, 0, 'R')
        
        # Reset position for question text, limit width to avoid overlapping brace
        pdf.set_xy(10, current_y)
        pdf.multi_cell(150, 10, question_text)
        
        # Options 2-column format
        pdf.set_font("Arial", '', 11)
        
        a_text = f"A.  {q.option_a}".encode('latin-1', 'replace').decode('latin-1')
        b_text = f"B.  {q.option_b}".encode('latin-1', 'replace').decode('latin-1')
        c_text = f"C.  {q.option_c}".encode('latin-1', 'replace').decode('latin-1')
        d_text = f"D.  {q.option_d}".encode('latin-1', 'replace').decode('latin-1')
        
        col_width = 90
        
        pdf.cell(col_width, 8, a_text, 0, 0)
        pdf.cell(col_width, 8, c_text, 0, 1)
        pdf.cell(col_width, 8, b_text, 0, 0)
        pdf.cell(col_width, 8, d_text, 0, 1)
        
        pdf.ln(2)
        
        y = pdf.get_y()
        pdf.line(10, y, 200, y)
        pdf.line(10, y + 1, 200, y + 1)
        pdf.ln(6)
    
    pdf_output = io.BytesIO()
    pdf_string = pdf.output(dest='S')
    pdf_output.write(pdf_string.encode('latin-1'))
    pdf_output.seek(0)
    
    return send_file(pdf_output, as_attachment=True, download_name=f"test_{test.id}.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)