import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Dashboard Module - v1.0
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


# Create nurse dashboard blueprint
nurse_bp = Blueprint('nurse_dashboard', __name__, url_prefix='/api/nurse')



def format_time(value):
    """Helper function to format time value - handles both time and timedelta"""
    if value is None:
        return ""
    # Handle timedelta (from MySQL TIME column)
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        period = "AM" if hours < 12 else "PM"
        hour_12 = hours % 12
        if hour_12 == 0:
            hour_12 = 12
        if seconds > 0:
            return f"{hour_12}:{minutes:02d}:{seconds:02d} {period}"
        return f"{hour_12}:{minutes:02d} {period}"
    # Handle time object
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    # Handle string
    if isinstance(value, str):
        return value
    return ""


def convert_to_time(value):
    """Convert timedelta or time to time object for comparisons"""
    if value is None:
        return None
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return time(hour=hours, minute=minutes, second=seconds)
    if isinstance(value, time):
        return value
    return None


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
# Get Dashboard Stats
# =========================================

@nurse_bp.route('/dashboard/stats', methods=['GET'])
@login_required
@nurse_required
def get_dashboard_stats():
    """Get nurse dashboard statistics"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Today's assists count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM assists a
                JOIN appointments app ON a.appointment_id = app.id
                WHERE a.nurse_id = ? 
                AND DATE(app.appointment_date) = date('now')
                AND app.status NOT IN ('cancelled')
            """, (nurse_id,))
            stats['assists_today'] = cursor.fetchone()['count']

            # Unique doctors count today
            cursor.execute("""
                SELECT COUNT(DISTINCT app.doctor_id) as count
                FROM assists a
                JOIN appointments app ON a.appointment_id = app.id
                WHERE a.nurse_id = ? 
                AND DATE(app.appointment_date) = date('now')
                AND app.doctor_id IS NOT NULL
            """, (nurse_id,))
            stats['doctors_today'] = cursor.fetchone()['count']

            # Independent procedures (nurse-only appointments)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE nurse_id = ? 
                AND DATE(appointment_date) = date('now')
                AND type = 'nurse_only'
                AND status NOT IN ('cancelled', 'completed')
            """, (nurse_id,))
            stats['independent_procedures'] = cursor.fetchone()['count']

            # Independent procedures yesterday for comparison
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE nurse_id = ? 
                AND DATE(appointment_date) = date(date('now'), '-1 days')
                AND type = 'nurse_only'
            """, (nurse_id,))
            yesterday_procedures = cursor.fetchone()['count']

            if yesterday_procedures > 0:
                stats['procedures_change'] = stats['independent_procedures'] - \
                    yesterday_procedures
            else:
                stats['procedures_change'] = stats['independent_procedures']

            # Pending tasks count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM tasks
                WHERE assigned_to = ? 
                AND status = 'pending'
            """, (nurse_id,))
            stats['pending_tasks'] = cursor.fetchone()['count']

            # Completed tasks today
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM tasks
                WHERE assigned_to = ? 
                AND status = 'completed'
                AND DATE(completed_at) = date('now')
            """, (nurse_id,))
            stats['completed_tasks'] = cursor.fetchone()['count']

            # Average rating (placeholder - from reviews table)
            stats['avg_rating'] = 4.8

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Dashboard stats error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500


# =========================================
# Get Today's Assists (by doctor)
# =========================================

@nurse_bp.route('/dashboard/assists', methods=['GET'])
@login_required
@nurse_required
def get_today_assists():
    """Get today's assists grouped by doctor"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        assists_by_doctor = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    d.id as doctor_id,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    d.specialization,
                    a.id as appointment_id,
                    a.start_time,
                    a.room,
                    p.id as patient_id,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    GROUP_CONCAT(s.name, ', ') as procedures
                FROM assists ass
                JOIN appointments a ON ass.appointment_id = a.id
                JOIN users d ON a.doctor_id = d.id
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE ass.nurse_id = ? 
                AND DATE(a.appointment_date) = date('now')
                AND a.status NOT IN ('cancelled')
                GROUP BY a.id, d.id, p.id
                ORDER BY d.last_name, a.start_time
            """, (nurse_id,))

            results = cursor.fetchall()

            # Group by doctor
            doctors_dict = {}
            for row in results:
                doctor_id = row['doctor_id']
                if doctor_id not in doctors_dict:
                    doctors_dict[doctor_id] = {
                        'doctor_id': doctor_id,
                        'doctor_name': f"Dr. {row['doctor_first']} {row['doctor_last']}",
                        'doctor_initials': f"{row['doctor_first'][0]}{row['doctor_last'][0]}",
                        'specialization': row['specialization'] or 'General Dentistry',
                        'patients': []
                    }

                doctors_dict[doctor_id]['patients'].append({
                    'id': row['patient_id'],
                    'appointment_id': row['appointment_id'],  # Add this line
                    'name': f"{row['patient_first']} {row['patient_last']}",
                    'initials': f"{row['patient_first'][0]}{row['patient_last'][0]}",
                    'time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'procedure': row['procedures'] or 'Assisting'
                })

            # Convert to list and add patient count
            for doctor in doctors_dict.values():
                doctor['patient_count'] = len(doctor['patients'])
                # Sort patients by time
                doctor['patients'].sort(key=lambda x: x['time'])
                assists_by_doctor.append(doctor)

        db.close()
        return jsonify({'success': True, 'assists': assists_by_doctor}), 200

    except Exception as e:
        print(f"Get assists error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch assists'}), 500


# =========================================
# Get Independent Procedures (Nurse-Only Appointments)
# =========================================

@nurse_bp.route('/dashboard/procedures', methods=['GET'])
@login_required
@nurse_required
def get_independent_procedures():
    """Get nurse's independent procedures for today"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        procedures = []

        print(f"=== DEBUG: Nurse ID = {nurse_id} ===")
        print(f"=== Current Date = {datetime.now().date()} ===")

        with db.cursor() as cursor:
            # Get nurse-only appointments for this specific nurse
            cursor.execute("""
                SELECT 
                    a.id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.type,
                    a.notes as appointment_notes,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    s.name as procedure_name,
                    s.duration_minutes
                FROM appointments a
                INNER JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.nurse_id = ? 
                AND DATE(a.appointment_date) = date('now')
                AND a.type = 'nurse_only'
                AND a.status NOT IN ('cancelled', 'completed')
                ORDER BY a.start_time
            """, (nurse_id,))

            results = cursor.fetchall()

            print(
                f"Found {len(results)} nurse-only appointments for nurse {nurse_id}")

            for row in results:
                print(
                    f"Processing: {row['first_name']} {row['last_name']} at {row['start_time']}")

                # Convert start_time to time object for comparison
                start_time_obj = convert_to_time(row['start_time'])
                time_status = "Scheduled"
                action = "view"

                if start_time_obj:
                    now = datetime.now()
                    current_time = now.time()

                    if start_time_obj > current_time:
                        # Calculate minutes until appointment
                        start_dt = datetime.combine(now.date(), start_time_obj)
                        minutes_until = (start_dt - now).total_seconds() // 60
                        if minutes_until <= 15:
                            time_status = "Now"
                            action = "start"
                        elif minutes_until <= 60:
                            time_status = f"In {int(minutes_until)} min"
                            action = "prepare"
                        else:
                            time_status = f"In {int(minutes_until)} min"
                            action = "view"
                    elif start_time_obj <= current_time:
                        time_status = "Overdue"
                        action = "view"

                # Calculate age
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                # Determine procedure name
                procedure_name = row['procedure_name']
                if not procedure_name:
                    if row['appointment_notes']:
                        procedure_name = row['appointment_notes'].split('\n')[
                            0][:50]
                    else:
                        procedure_name = 'Nurse Procedure'

                procedures.append({
                    'id': row['id'],
                    'patient_id': row['patient_id'],
                    'patient_name': f"{row['first_name']} {row['last_name']}",
                    'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_age': age,
                    'patient_gender': row['gender'],
                    'patient_phone': row['phone'],
                    'patient_allergies': row['allergies'],
                    'procedure': procedure_name,
                    'time': format_time(row['start_time']),
                    'end_time': format_time(row['end_time']),
                    'room': row['room'] or 'TBD',
                    'time_status': time_status,
                    'action': action,
                    'status': row['status'],
                    'duration': row['duration_minutes'] or 30,
                    'notes': row['appointment_notes']
                })

        db.close()

        print(f"Returning {len(procedures)} procedures to frontend")
        return jsonify({'success': True, 'procedures': procedures}), 200

    except Exception as e:
        print(f"Get procedures error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch procedures: {str(e)}'}), 500


# =========================================
# Get My Tasks
# =========================================

@nurse_bp.route('/dashboard/tasks', methods=['GET'])
@login_required
@nurse_required
def get_my_tasks():
    """Get nurse's tasks for dashboard"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        tasks = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    task_name,
                    description,
                    due_date,
                    priority,
                    status,
                    created_at
                FROM tasks
                WHERE assigned_to = ? 
                AND status != 'completed'
                ORDER BY 
                    CASE priority 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        WHEN 'low' THEN 3 
                    END,
                    due_date ASC
                LIMIT 4
            """, (nurse_id,))

            results = cursor.fetchall()

            for row in results:
                due_time = format_time(
                    row['due_date']) if row['due_date'] else 'No deadline'

                tasks.append({
                    'id': row['id'],
                    'name': row['task_name'],
                    'description': row['description'] or '',
                    'due_time': due_time,
                    'priority': row['priority'],
                    'status': row['status']
                })

        db.close()
        return jsonify({'success': True, 'tasks': tasks}), 200

    except Exception as e:
        print(f"Get tasks error: {e}")
        return jsonify({'error': 'Failed to fetch tasks'}), 500


# =========================================
# Get Recent Notes
# =========================================

@nurse_bp.route('/dashboard/notes', methods=['GET'])
@login_required
@nurse_required
def get_recent_notes():
    """Get recent medical notes written by this nurse"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        notes = []

        with db.cursor() as cursor:
            # Get notes written by this nurse
            cursor.execute("""
                SELECT 
                    mn.id,
                    mn.content,
                    mn.note_date,
                    mn.note_type,
                    p.first_name,
                    p.last_name,
                    p.id as patient_id
                FROM medical_notes mn
                JOIN patients p ON mn.patient_id = p.id
                WHERE mn.author_id = ?
                ORDER BY mn.note_date DESC
                LIMIT 3
            """, (nurse_id,))

            results = cursor.fetchall()

            for row in results:
                # Get time ago
                time_ago = get_time_ago(row['note_date'])

                # Get first line or truncate content
                content = row['content'][:100] + \
                    '...' if len(row['content']) > 100 else row['content']

                notes.append({
                    'id': row['id'],
                    'title': f"{row['note_type'].replace('-', ' ').title()} - {row['first_name']} {row['last_name']}",
                    'time_ago': time_ago,
                    'content': content,
                    'patient_name': f"{row['first_name']} {row['last_name']}",
                    'patient_id': row['patient_id'],
                    'note_type': row['note_type']
                })

        db.close()
        return jsonify({'success': True, 'notes': notes}), 200

    except Exception as e:
        print(f"Get notes error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch notes'}), 500


# =========================================
# Get Patient Details
# =========================================

@nurse_bp.route('/patient/<int:patient_id>', methods=['GET'])
@login_required
@nurse_required
def get_patient_details(patient_id):
    """Get patient details for nurse"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.email,
                    p.allergies,
                    p.chronic_conditions,
                    p.current_medications,
                    p.medical_alerts
                FROM patients p
                WHERE p.id = ? AND p.status = 'active'
            """, (patient_id,))

            patient = cursor.fetchone()

            if not patient:
                return jsonify({'error': 'Patient not found'}), 404

            # Calculate age
            age = None
            if patient['dob']:
                today = datetime.now().date()
                age = today.year - patient['dob'].year - (
                    (today.month, today.day) < (patient['dob'].month, patient['dob'].day))

            # Get latest vitals
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

            result = {
                'id': patient['id'],
                'patient_number': patient['patient_number'],
                'first_name': patient['first_name'],
                'last_name': patient['last_name'],
                'full_name': f"{patient['first_name']} {patient['last_name']}",
                'initials': f"{patient['first_name'][0]}{patient['last_name'][0]}",
                'age': age,
                'gender': patient['gender'],
                'phone': patient['phone'],
                'email': patient['email'],
                'allergies': patient['allergies'],
                'chronic_conditions': patient['chronic_conditions'],
                'current_medications': patient['current_medications'],
                'medical_alerts': patient['medical_alerts'],
                'vitals': {
                    'bp_systolic': vitals['bp_systolic'] if vitals else None,
                    'bp_diastolic': vitals['bp_diastolic'] if vitals else None,
                    'heart_rate': vitals['heart_rate'] if vitals else None,
                    'temperature': vitals['temperature'] if vitals else None,
                    'oxygen_saturation': vitals['oxygen_saturation'] if vitals else None
                }
            }

        db.close()
        return jsonify({'success': True, 'patient': result}), 200

    except Exception as e:
        print(f"Get patient details error: {e}")
        return jsonify({'error': 'Failed to fetch patient details'}), 500


# =========================================
# Update Task Status
# =========================================

@nurse_bp.route('/task/<int:task_id>/complete', methods=['PUT'])
@login_required
@nurse_required
def complete_task(task_id):
    """Mark a task as completed"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE tasks 
                SET status = 'completed', 
                    completed_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE id = ? AND assigned_to = ?
            """, (task_id, nurse_id))

            if cursor.rowcount == 0:
                return jsonify({'error': 'Task not found'}), 404

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_TASK', 'tasks', ?, ?)
            """, (nurse_id, task_id, json.dumps({'status': 'completed'})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Task completed successfully'}), 200

    except Exception as e:
        print(f"Complete task error: {e}")
        return jsonify({'error': 'Failed to complete task'}), 500


# =========================================
# Helper Functions
# =========================================

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
