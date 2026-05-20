# AI MCQ Generator & Online Test Platform

An AI-powered web application that generates multiple-choice questions dynamically using a transformer model. Users can register, log in, create tests by topic and difficulty, attempt them online, download PDFs, and view test history.

---

## Features

- User registration and login
- Secure password hashing
- AI-generated MCQs from custom topics
- Difficulty selection (Easy / Medium / Hard)
- Online test interface
- Automatic score calculation
- Test history tracking
- PDF download for generated tests
- SQLite database storage
- Persistent user sessions

---

## Tech Stack

### Backend
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Werkzeug

### AI / NLP
- Hugging Face Transformers
- FLAN-T5 Base
- PyTorch

### Database
- SQLite

### Frontend
- HTML
- CSS
- Jinja2

### PDF
- FPDF

---

## Project Architecture

User → Flask Routes → AI Model → SQLite → Web UI / PDF

The system:
1. Accepts user topic input
2. Uses FLAN-T5 to generate questions
3. Generates correct and incorrect options
4. Saves tests/questions in SQLite
5. Allows online test attempts
6. Stores scores/history
7. Exports tests as PDF

---

## Database Tables

### User
Stores registered users.

| Column | Description |
|---|---|
| id | User ID |
| username | Login name |
| password_hash | Encrypted password |

### Test
Stores generated tests.

| Column | Description |
|---|---|
| id | Test ID |
| user_id | Owner |
| topic | Topic |
| difficulty | Difficulty |
| created_at | Timestamp |
| main_heading | Title |

### Question
Stores generated MCQs.

| Column | Description |
|---|---|
| test_id | Related test |
| question_text | Question |
| option_a | Option A |
| option_b | Option B |
| option_c | Option C |
| option_d | Option D |
| correct_answer | Answer |

### Attempt
Stores user scores.

| Column | Description |
|---|---|
| user_id | User |
| test_id | Test |
| score | Marks |
| max_score | Total |
| taken_at | Timestamp |

---

## Folder Structure

mcq_app/
├── app.py  
├── requirements.txt  
├── instance/  
│   └── mcq.db  
├── static/  
│   └── style.css  
├── templates/  
│   ├── base.html  
│   ├── login.html  
│   ├── register.html  
│   ├── index.html  
│   ├── generate.html  
│   ├── take_test.html  
│   └── history.html  
├── screenshots/  
└── README.md  

---

## Installation

Clone repository:

```bash
git clone <your-repo-url>
cd mcq_app
