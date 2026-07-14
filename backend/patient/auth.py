# =========================================
# Perfections Dental Services
# Patient Portal — Authentication
#
# Deliberately separate from backend/auth.py (staff auth): patients are not
# `users` rows, they're `patients` rows, and use their own session keys so
# a staff member and a patient can never be confused with one another.
# =========================================

import re
from functools import wraps

from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

patient_bp = Blueprint('patient_auth', __name__, url_prefix='/api/patient/auth')

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def patient_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'patient_id' not in session:
            return jsonify({'error': 'Authentication required', 'redirect': '/pages/patient/login.html'}), 401
        return f(*args, **kwargs)
    return decorated


def _patient_public(row):
    return {
        'id': row['id'],
        'patient_code': row['patient_number'],
        'first_name': row['first_name'],
        'last_name': row['last_name'],
        'name': f"{row['first_name']} {row['last_name']}",
        'email': row['email'],
        'phone': row['phone'],
    }


# =========================================
# Register — activates portal access for an existing patient record
# (matched by phone, since reception creates the clinical record first)
# or creates a brand-new self-service patient if no match exists.
# =========================================
@patient_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''

    if not phone or not password:
        return jsonify({'error': 'Phone and password are required'}), 400
    if email and not EMAIL_RE.match(email):
        return jsonify({'error': 'Invalid email format'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM patients WHERE phone = ?", (phone,))
            existing = cursor.fetchone()

            password_hash = generate_password_hash(password)

            if existing:
                if existing['portal_active']:
                    return jsonify({'error': 'An account already exists for this phone number. Please log in.'}), 409
                cursor.execute("""
                    UPDATE patients
                    SET password_hash = ?, portal_active = 1,
                        email = COALESCE(NULLIF(?, ''), email),
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (password_hash, email, existing['id']))
                patient_id = existing['id']
            else:
                if not first_name or not last_name:
                    return jsonify({'error': 'First and last name are required for a new patient'}), 400
                cursor.execute("""
                    INSERT INTO patients (first_name, last_name, email, phone, password_hash, portal_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (first_name, last_name, email or None, phone, password_hash))
                patient_id = cursor.lastrowid
                cursor.execute("""
                    UPDATE patients SET patient_number = ? WHERE id = ?
                """, (f"PT-{patient_id:04d}", patient_id))

            db.commit()

            cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
            patient = cursor.fetchone()

        session.clear()
        session['patient_id'] = patient['id']
        session['patient'] = _patient_public(patient)
        session.permanent = True

        return jsonify({
            'success': True,
            'message': 'Account created',
            'patient': _patient_public(patient),
            'redirect': '/pages/patient/dashboard.html',
        }), 201
    except Exception as e:
        db.rollback()
        print(f"Patient register error: {e}")
        return jsonify({'error': 'Registration failed'}), 500
    finally:
        db.close()


@patient_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identifier = (data.get('phone') or data.get('email') or '').strip()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({'error': 'Phone/email and password are required'}), 400

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM patients
                WHERE (phone = ? OR email = ?) AND portal_active = 1
            """, (identifier, identifier.lower()))
            patient = cursor.fetchone()

        if not patient or not patient['password_hash'] or not check_password_hash(patient['password_hash'], password):
            return jsonify({'error': 'Invalid credentials'}), 401

        session.clear()
        session['patient_id'] = patient['id']
        session['patient'] = _patient_public(patient)
        session.permanent = True

        return jsonify({
            'success': True,
            'patient': _patient_public(patient),
            'redirect': '/pages/patient/dashboard.html',
        }), 200
    except Exception as e:
        print(f"Patient login error: {e}")
        return jsonify({'error': 'Login failed'}), 500
    finally:
        db.close()


@patient_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'redirect': '/pages/patient/login.html'}), 200


@patient_bp.route('/session', methods=['GET'])
def check_session():
    if 'patient_id' in session:
        return jsonify({'authenticated': True, 'patient': session.get('patient')}), 200
    return jsonify({'authenticated': False}), 200
