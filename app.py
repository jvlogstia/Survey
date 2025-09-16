from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///surveycraft.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    surveys = db.relationship('Survey', backref='creator', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Survey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft, active, closed, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    questions = db.relationship('Question', backref='survey', lazy=True, cascade="all, delete-orphan")
    responses = db.relationship('Response', backref='survey', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # text, multiple, checkbox, dropdown, rating, etc.
    text = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    required = db.Column(db.Boolean, default=False)
    options = db.Column(db.Text)  # JSON string for options
    order = db.Column(db.Integer, default=0)

class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    response_data = db.Column(db.Text)  # JSON string of responses
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password')
    
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered')
            return redirect(url_for('signup'))
        
        # Create new user
        new_user = User(name=name, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        session['user_id'] = new_user.id
        session['user_name'] = new_user.name
        
        return redirect(url_for('index'))
    
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# API Routes for Surveys
@app.route('/api/surveys', methods=['GET'])
def get_surveys():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    surveys = Survey.query.filter_by(user_id=user_id).all()
    
    result = []
    for survey in surveys:
        result.append({
            'id': survey.id,
            'title': survey.title,
            'description': survey.description,
            'status': survey.status,
            'created_at': survey.created_at.isoformat(),
            'updated_at': survey.updated_at.isoformat(),
            'responses_count': len(survey.responses)
        })
    
    return jsonify(result)

@app.route('/api/surveys', methods=['POST'])
def create_survey():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    user_id = session['user_id']
    
    new_survey = Survey(
        title=data['title'],
        description=data.get('description', ''),
        user_id=user_id
    )
    
    db.session.add(new_survey)
    db.session.commit()
    
    return jsonify({
        'id': new_survey.id,
        'title': new_survey.title,
        'description': new_survey.description,
        'status': new_survey.status,
        'created_at': new_survey.created_at.isoformat()
    }), 201

@app.route('/api/surveys/<int:survey_id>', methods=['GET'])
def get_survey(survey_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    survey = Survey.query.get_or_404(survey_id)
    
    if survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    questions = []
    for question in survey.questions:
        q_data = {
            'id': question.id,
            'type': question.type,
            'text': question.text,
            'description': question.description,
            'required': question.required,
            'order': question.order
        }
        
        if question.options:
            q_data['options'] = json.loads(question.options)
        
        questions.append(q_data)
    
    return jsonify({
        'id': survey.id,
        'title': survey.title,
        'description': survey.description,
        'status': survey.status,
        'created_at': survey.created_at.isoformat(),
        'updated_at': survey.updated_at.isoformat(),
        'questions': questions
    })

@app.route('/api/surveys/<int:survey_id>', methods=['PUT'])
def update_survey(survey_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    survey = Survey.query.get_or_404(survey_id)
    
    if survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    
    survey.title = data.get('title', survey.title)
    survey.description = data.get('description', survey.description)
    survey.status = data.get('status', survey.status)
    survey.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'id': survey.id,
        'title': survey.title,
        'description': survey.description,
        'status': survey.status,
        'updated_at': survey.updated_at.isoformat()
    })

@app.route('/api/surveys/<int:survey_id>', methods=['DELETE'])
def delete_survey(survey_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    survey = Survey.query.get_or_404(survey_id)
    
    if survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    db.session.delete(survey)
    db.session.commit()
    
    return '', 204

# API Routes for Questions
@app.route('/api/surveys/<int:survey_id>/questions', methods=['POST'])
def create_question(survey_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    survey = Survey.query.get_or_404(survey_id)
    
    if survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    
    new_question = Question(
        survey_id=survey_id,
        type=data['type'],
        text=data['text'],
        description=data.get('description', ''),
        required=data.get('required', False),
        options=json.dumps(data.get('options', [])),
        order=data.get('order', 0)
    )
    
    db.session.add(new_question)
    db.session.commit()
    
    return jsonify({
        'id': new_question.id,
        'type': new_question.type,
        'text': new_question.text,
        'description': new_question.description,
        'required': new_question.required,
        'options': json.loads(new_question.options) if new_question.options else [],
        'order': new_question.order
    }), 201

@app.route('/api/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    question = Question.query.get_or_404(question_id)
    
    if question.survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    
    question.type = data.get('type', question.type)
    question.text = data.get('text', question.text)
    question.description = data.get('description', question.description)
    question.required = data.get('required', question.required)
    question.options = json.dumps(data.get('options', json.loads(question.options) if question.options else []))
    question.order = data.get('order', question.order)
    
    db.session.commit()
    
    return jsonify({
        'id': question.id,
        'type': question.type,
        'text': question.text,
        'description': question.description,
        'required': question.required,
        'options': json.loads(question.options) if question.options else [],
        'order': question.order
    })

@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    question = Question.query.get_or_404(question_id)
    
    if question.survey.user_id != session['user_id']:
        return jsonify({'error': 'Forbidden'}), 403
    
    db.session.delete(question)
    db.session.commit()
    
    return '', 204

# API Route for Submitting Responses
@app.route('/api/surveys/<int:survey_id>/responses', methods=['POST'])
def submit_response(survey_id):
    survey = Survey.query.get_or_404(survey_id)
    
    if survey.status != 'active':
        return jsonify({'error': 'Survey is not active'}), 400
    
    data = request.get_json()
    
    new_response = Response(
        survey_id=survey_id,
        user_id=session.get('user_id'),
        response_data=json.dumps(data)
    )
    
    db.session.add(new_response)
    db.session.commit()
    
    return jsonify({'id': new_response.id}), 201

# API Route for Dashboard Stats
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    # Count surveys
    surveys_count = Survey.query.filter_by(user_id=user_id).count()
    
    # Count responses
    responses_count = Response.query.join(Survey).filter(Survey.user_id == user_id).count()
    
    # Calculate completion rate (dummy calculation for demo)
    completion_rate = 74  # In a real app, this would be calculated
    
    # Active users (dummy calculation for demo)
    active_users = 12
    
    return jsonify({
        'surveys': surveys_count,
        'responses': responses_count,
        'completion': completion_rate,
        'active': active_users
    })

# API Route for Recent Activity
@app.route('/api/dashboard/activity', methods=['GET'])
def get_recent_activity():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    # Get recent surveys
    recent_surveys = Survey.query.filter_by(user_id=user_id).order_by(Survey.created_at.desc()).limit(5).all()
    
    activity = []
    for survey in recent_surveys:
        activity.append({
            'type': 'survey',
            'title': f'Created "{survey.title}"',
            'time': survey.created_at.strftime('%b %d, %Y')
        })
    
    return jsonify(activity)

if __name__ == '__main__':
    app.run(debug=True)