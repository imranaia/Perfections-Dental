import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Notes Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create notes blueprint
notes_bp = Blueprint('nurse_notes', __name__, url_prefix='/api/nurse/notes')



def format_time(value):
    """Helper function to format time value"""
    if value is None:
        return ""
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        period = "AM" if hours < 12 else "PM"
        hour_12 = hours % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{hour_12}:{minutes:02d} {period}"
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    if isinstance(value, str):
        return value
    return ""


def get_time_ago(date):
    """Get time ago string"""
    if not date:
        return ''
    now = datetime.now()
    diff = now - date

    if diff.days > 30:
        return date.strftime('%b %d, %Y')
    elif diff.days > 7:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def nurse_required(f):
    """Decorator to require nurse role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['nurse', 'superadmin']:
            return jsonify({'error': 'Access denied. Nurse role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Today's Patients for Nurse
# =========================================

@notes_bp.route('/today-patients', methods=['GET'])
@login_required
@nurse_required
def get_today_patients():
    """Get all patients the nurse is working with today"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            # Get appointments where nurse is assigned (assists or nurse-only)
            cursor.execute("""
                SELECT DISTINCT
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    p.chronic_conditions,
                    p.medical_alerts,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.type,
                    a.notes as appointment_notes,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    s.name as service_name
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE (a.nurse_id = ? OR a.id IN (
                    SELECT appointment_id FROM assists WHERE nurse_id = ?
                ))
                AND DATE(a.appointment_date) = date('now')
                AND a.status NOT IN ('cancelled', 'completed')
                ORDER BY a.start_time
            """, (nurse_id, nurse_id))

            results = cursor.fetchall()

            for row in results:
                # Calculate age
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                # Check if there's an existing note for this appointment
                cursor.execute("""
                    SELECT id, content, note_date, note_type
                    FROM medical_notes
                    WHERE appointment_id = ? AND author_id = ?
                    ORDER BY note_date DESC
                    LIMIT 1
                """, (row['appointment_id'], nurse_id))
                existing_note = cursor.fetchone()

                patients.append({
                    'id': row['id'],
                    'patient_id': row['id'],
                    'appointment_id': row['appointment_id'],
                    'patient_number': row['patient_number'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'full_name': f"{row['first_name']} {row['last_name']}",
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'age': age,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'type': row['type'],
                    'doctor': f"Dr. {row['doctor_first']} {row['doctor_last']}" if row['doctor_first'] else 'Nurse Only',
                    'procedure': row['service_name'] or 'Assisting',
                    'allergies': row['allergies'],
                    'chronic_conditions': row['chronic_conditions'],
                    'medical_alerts': row['medical_alerts'],
                    'has_notes': existing_note is not None,
                    'existing_note_id': existing_note['id'] if existing_note else None,
                    'existing_note_content': existing_note['content'] if existing_note else '',
                    'existing_note_type': existing_note['note_type'] if existing_note else ''
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get today patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Patient Vitals
# =========================================

@notes_bp.route('/vitals/<int:patient_id>', methods=['GET'])
@login_required
@nurse_required
def get_patient_vitals(patient_id):
    """Get latest vitals for a patient"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    bp_systolic,
                    bp_diastolic,
                    heart_rate,
                    temperature,
                    oxygen_saturation,
                    recorded_at
                FROM vitals
                WHERE patient_id = ?
                ORDER BY recorded_at DESC
                LIMIT 1
            """, (patient_id,))
            vitals = cursor.fetchone()

        db.close()
        return jsonify({
            'success': True,
            'vitals': vitals or {}
        }), 200

    except Exception as e:
        print(f"Get vitals error: {e}")
        return jsonify({'error': 'Failed to fetch vitals'}), 500


# =========================================
# Save or Update Medical Note
# =========================================

@notes_bp.route('/save', methods=['POST'])
@login_required
@nurse_required
def save_medical_note():
    """Save or update medical note for an appointment"""
    try:
        data = request.get_json()
        nurse_id = session.get('user_id')

        patient_id = data.get('patient_id')
        appointment_id = data.get('appointment_id')
        existing_note_id = data.get('existing_note_id')
        note_type = data.get('note_type', 'general')
        content = data.get('content', '')
        vitals = data.get('vitals', {})

        if not patient_id or not appointment_id:
            return jsonify({'error': 'Patient ID and Appointment ID required'}), 400

        if not content:
            return jsonify({'error': 'Note content is required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get patient name for note header
            cursor.execute(
                "SELECT first_name, last_name FROM patients WHERE id = ?", (patient_id,))
            patient = cursor.fetchone()

            # Build formatted note with timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            formatted_content = f"=== NURSE NOTES ===\nDate: {timestamp}\nNurse: {session.get('name', 'Nurse')}\n\n{content}"

            # Also add vitals if provided
            if vitals.get('bp_systolic') or vitals.get('heart_rate'):
                formatted_content += "\n\n=== VITAL SIGNS ===\n"
                if vitals.get('bp_systolic') and vitals.get('bp_diastolic'):
                    formatted_content += f"BP: {vitals['bp_systolic']}/{vitals['bp_diastolic']}\n"
                if vitals.get('heart_rate'):
                    formatted_content += f"Heart Rate: {vitals['heart_rate']} bpm\n"
                if vitals.get('temperature'):
                    formatted_content += f"Temperature: {vitals['temperature']}°C\n"
                if vitals.get('oxygen_saturation'):
                    formatted_content += f"O2 Saturation: {vitals['oxygen_saturation']}%\n"

            # Check if note exists
            if existing_note_id:
                # Update existing note
                cursor.execute("""
                    UPDATE medical_notes 
                    SET content = ?, 
                        note_type = ?,
                        updated_at = datetime('now')
                    WHERE id = ? AND author_id = ?
                """, (formatted_content, note_type, existing_note_id, nurse_id))
                message = "Note updated successfully"
                note_id = existing_note_id
            else:
                # Create new note
                cursor.execute("""
                    INSERT INTO medical_notes (patient_id, author_id, appointment_id, note_date, note_type, content)
                    VALUES (?, ?, ?, datetime('now'), ?, ?)
                """, (patient_id, nurse_id, appointment_id, note_type, formatted_content))
                note_id = cursor.lastrowid
                message = "Note saved successfully"

            # Save vitals if provided
            if vitals.get('bp_systolic') or vitals.get('heart_rate') or vitals.get('temperature'):
                cursor.execute("""
                    INSERT INTO vitals (patient_id, appointment_id, recorded_by, recorded_at, 
                                       bp_systolic, bp_diastolic, heart_rate, temperature, oxygen_saturation)
                    VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)
                """, (
                    patient_id, appointment_id, nurse_id,
                    vitals.get('bp_systolic'), vitals.get('bp_diastolic'),
                    vitals.get('heart_rate'), vitals.get('temperature'),
                    vitals.get('oxygen_saturation')
                ))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'SAVE_NOTE', 'medical_notes', ?, ?)
            """, (nurse_id, note_id, json.dumps({'note_type': note_type})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': message,
            'note_id': note_id
        }), 200

    except Exception as e:
        print(f"Save note error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to save note'}), 500


# =========================================
# Get Recent Notes by Nurse
# =========================================

@notes_bp.route('/recent', methods=['GET'])
@login_required
@nurse_required
def get_recent_notes():
    """Get recent notes written by this nurse"""
    try:
        nurse_id = session.get('user_id')
        limit = request.args.get('limit', 10, type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        notes = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    mn.id,
                    mn.content,
                    mn.note_date,
                    mn.note_type,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    a.id as appointment_id,
                    a.start_time,
                    a.room
                FROM medical_notes mn
                JOIN patients p ON mn.patient_id = p.id
                LEFT JOIN appointments a ON mn.appointment_id = a.id
                WHERE mn.author_id = ?
                ORDER BY mn.note_date DESC
                LIMIT ?
            """, (nurse_id, limit))

            results = cursor.fetchall()

            for row in results:
                # Extract first line for preview
                content_preview = row['content'][:100] + \
                    '...' if len(row['content']) > 100 else row['content']
                time_ago = get_time_ago(row['note_date'])

                notes.append({
                    'id': row['id'],
                    'patient_id': row['patient_id'],
                    'patient_name': f"{row['first_name']} {row['last_name']}",
                    'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number': row['patient_number'],
                    'appointment_id': row['appointment_id'],
                    'appointment_time': format_time(row['start_time']) if row['start_time'] else '',
                    'room': row['room'] or 'TBD',
                    'note_type': row['note_type'],
                    'content': content_preview,
                    'full_content': row['content'],
                    'date': row['note_date'].strftime('%b %d, %Y %I:%M %p') if row['note_date'] else '',
                    'time_ago': time_ago
                })

        db.close()
        return jsonify({'success': True, 'notes': notes}), 200

    except Exception as e:
        print(f"Get recent notes error: {e}")
        return jsonify({'error': 'Failed to fetch notes'}), 500


# =========================================
# Get Single Note Details
# =========================================

@notes_bp.route('/<int:note_id>', methods=['GET'])
@login_required
@nurse_required
def get_note_details(note_id):
    """Get full details of a specific note"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    mn.id,
                    mn.content,
                    mn.note_date,
                    mn.note_type,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    p.chronic_conditions,
                    p.current_medications,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    u.first_name as nurse_first,
                    u.last_name as nurse_last
                FROM medical_notes mn
                JOIN patients p ON mn.patient_id = p.id
                LEFT JOIN appointments a ON mn.appointment_id = a.id
                JOIN users u ON mn.author_id = u.id
                WHERE mn.id = ? AND mn.author_id = ?
            """, (note_id, nurse_id))

            note = cursor.fetchone()

            if not note:
                return jsonify({'error': 'Note not found'}), 404

            # Calculate age
            age = None
            if note['dob']:
                today = datetime.now().date()
                age = today.year - \
                    note['dob'].year - ((today.month, today.day)
                                        < (note['dob'].month, note['dob'].day))

            result = {
                'id': note['id'],
                'content': note['content'],
                'full_content': note['content'],
                'note_date': note['note_date'].strftime('%b %d, %Y %I:%M %p') if note['note_date'] else '',
                'note_type': note['note_type'],
                'patient': {
                    'id': note['patient_id'],
                    'name': f"{note['first_name']} {note['last_name']}",
                    'initials': f"{note['first_name'][0]}{note['last_name'][0]}",
                    'patient_number': note['patient_number'],
                    'age': age,
                    'gender': note['gender'],
                    'phone': note['phone'],
                    'allergies': note['allergies'],
                    'chronic_conditions': note['chronic_conditions'],
                    'current_medications': note['current_medications']
                },
                'appointment': {
                    'id': note['appointment_id'],
                    'time': format_time(note['start_time']) if note['start_time'] else '',
                    'end_time': format_time(note['end_time']) if note['end_time'] else '',
                    'room': note['room'] or 'TBD',
                    'status': note['status']
                },
                'author': {
                    'name': f"Nurse {note['nurse_first']} {note['nurse_last']}"
                }
            }

        db.close()
        return jsonify({'success': True, 'note': result}), 200

    except Exception as e:
        print(f"Get note details error: {e}")
        return jsonify({'error': 'Failed to fetch note details'}), 500


# =========================================
# Delete Note
# =========================================

@notes_bp.route('/<int:note_id>', methods=['DELETE'])
@login_required
@nurse_required
def delete_note(note_id):
    """Delete a medical note"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                DELETE FROM medical_notes 
                WHERE id = ? AND author_id = ?
            """, (note_id, nurse_id))

            if cursor.rowcount == 0:
                return jsonify({'error': 'Note not found'}), 404

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_NOTE', 'medical_notes', ?)
            """, (nurse_id, note_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Note deleted successfully'}), 200

    except Exception as e:
        print(f"Delete note error: {e}")
        return jsonify({'error': 'Failed to delete note'}), 500


# =========================================
# Search Patients (for the day)
# =========================================

@notes_bp.route('/search', methods=['GET'])
@login_required
@nurse_required
def search_patients():
    """Search patients for the current day"""
    try:
        nurse_id = session.get('user_id')
        query = request.args.get('q', '')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            search_term = f"%{query}%"
            cursor.execute("""
                SELECT DISTINCT
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.dob,
                    p.gender,
                    p.phone,
                    a.id as appointment_id,
                    a.start_time,
                    a.room,
                    a.status,
                    s.name as service_name
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE (a.nurse_id = ? OR a.id IN (
                    SELECT appointment_id FROM assists WHERE nurse_id = ?
                ))
                AND DATE(a.appointment_date) = date('now')
                AND (p.first_name LIKE ? OR p.last_name LIKE ? OR p.patient_number LIKE ? OR p.phone LIKE ?)
                AND a.status NOT IN ('cancelled', 'completed')
                ORDER BY a.start_time
            """, (nurse_id, nurse_id, search_term, search_term, search_term, search_term))

            results = cursor.fetchall()

            for row in results:
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                patients.append({
                    'id': row['id'],
                    'patient_id': row['id'],
                    'appointment_id': row['appointment_id'],
                    'full_name': f"{row['first_name']} {row['last_name']}",
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number': row['patient_number'],
                    'age': age,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'procedure': row['service_name'] or 'Assisting',
                    'status': row['status']
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Search patients error: {e}")
        return jsonify({'error': 'Failed to search patients'}), 500


# =========================================
# clinic settings for printing
# =========================================

@notes_bp.route('/clinic-settings', methods=['GET'])
@login_required
@nurse_required
def get_clinic_settings():
    """Get clinic settings for printing"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        settings = {}

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT setting_key, setting_value
                FROM clinic_settings
            """)
            results = cursor.fetchall()
            for row in results:
                key = row['setting_key'].replace('clinic_', '')
                settings[key] = row['setting_value']

        db.close()
        return jsonify({'success': True, 'settings': settings}), 200

    except Exception as e:
        print(f"Get clinic settings error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch settings'}), 500
