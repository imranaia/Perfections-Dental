import sqlite3
# =========================================
# Perfections Dental Services
# Nurse My Assists Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta, time
import json
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create my assists blueprint
my_assists_bp = Blueprint('nurse_my_assists', __name__,
                          url_prefix='/api/nurse/assists')



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


def convert_to_time(value):
    """Convert timedelta or time to time object"""
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


def get_status_badge(status):
    """Get status badge styling - based on appointment status, not assist status"""
    badges = {
        'scheduled': {'text': 'Scheduled', 'class': 'info'},
        'checked_in': {'text': 'Checked In', 'class': 'success'},
        'waiting': {'text': 'Waiting', 'class': 'warning'},
        'in_progress': {'text': 'In Progress', 'class': 'warning'},
        'completed': {'text': 'Completed', 'class': 'info'},
        'cancelled': {'text': 'Cancelled', 'class': 'error'}
    }
    return badges.get(status, {'text': status.title(), 'class': 'info'})


def get_instruments_for_procedure(procedure):
    """Get instruments needed for a procedure"""
    instruments_map = {
        'Extraction': ['Forceps', 'Elevator', 'Gauze', 'Suction tip', 'Local anesthetic', 'Needle holder', 'Suture'],
        'Root Canal': ['Endo motor', 'Files', 'Gutta percha', 'Sealer', 'Rubber dam', 'Irrigant', 'Paper points'],
        'Filling': ['Handpiece', 'Bur', 'Composite', 'Bonding agent', 'Curing light', 'Matrix band', 'Wedges'],
        'Cleaning': ['Scaler', 'Curette', 'Prophy angle', 'Polishing paste', 'Suction', 'Mirror', 'Explorer'],
        'Crown': ['Handpiece', 'Bur', 'Impression material', 'Tray', 'Temporary crown', 'Cement', 'Articulating paper'],
        'Consultation': ['Mirror', 'Explorer', 'Probe', 'X-ray viewer', 'Treatment plan form', 'Consent form'],
        'Surgical': ['Scalpel', 'Retractor', 'Hemostat', 'Needle holder', 'Suture', 'Suction', 'Gauze'],
        'Sterilize': ['Autoclave', 'Instrument cassettes', 'Sterilization pouches', 'Chemical indicators'],
        'Restock': ['Inventory list', 'Stock count sheet', 'Storage containers'],
        'Prepare': ['Basic tray', 'Gloves', 'Mask', 'Gown', 'Drapes']
    }

    procedure_lower = procedure.lower()
    for key, instruments in instruments_map.items():
        if key.lower() in procedure_lower:
            return instruments

    return ['Basic tray', 'Mirror', 'Explorer', 'Gauze', 'Suction', 'Gloves', 'Mask']


# =========================================
# Get All Assists for Nurse
# =========================================

@my_assists_bp.route('/', methods=['GET'])
@login_required
@nurse_required
def get_my_assists():
    """Get all assists for the logged-in nurse"""
    try:
        nurse_id = session.get('user_id')
        filter_type = request.args.get('filter', 'today')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        assists = []
        stats = {}

        with db.cursor() as cursor:
            # Get assists for today
            cursor.execute("""
                SELECT 
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.status as appointment_status,
                    a.room,
                    a.type,
                    d.id as doctor_id,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    d.specialization,
                    p.id as patient_id,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    p.patient_number,
                    p.phone,
                    p.dob,
                    ass.id as assist_id,
                    ass.status as assist_status,
                    ass.notes as assist_notes
                FROM assists ass
                JOIN appointments a ON ass.appointment_id = a.id
                JOIN users d ON a.doctor_id = d.id
                JOIN patients p ON a.patient_id = p.id
                WHERE ass.nurse_id = ?
                AND DATE(a.appointment_date) = date('now')
                AND a.status NOT IN ('cancelled')
                ORDER BY d.last_name, a.start_time
            """, (nurse_id,))

            results = cursor.fetchall()

            # Get procedures separately for each appointment
            procedures_map = {}
            for row in results:
                appt_id = row['appointment_id']
                cursor.execute("""
                    SELECT GROUP_CONCAT(s.name, ', ') as procedures
                    FROM appointment_services ast
                    JOIN services s ON ast.service_id = s.id
                    WHERE ast.appointment_id = ?
                """, (appt_id,))
                proc_result = cursor.fetchone()
                procedures_map[appt_id] = proc_result['procedures'] if proc_result else 'Consultation'

            # Apply filter - based on assist completion status
            filtered_results = results
            if filter_type == 'completed':
                filtered_results = [
                    r for r in results if r['assist_status'] == 'completed']
            elif filter_type == 'upcoming':
                filtered_results = [
                    r for r in results if r['assist_status'] != 'completed']
            # 'today' filter shows all (both assigned and completed)

            # Group by doctor
            doctors_dict = {}
            for row in filtered_results:
                doctor_id = row['doctor_id']
                if doctor_id not in doctors_dict:
                    doctors_dict[doctor_id] = {
                        'doctor_id': doctor_id,
                        'doctor_name': f"Dr. {row['doctor_first']} {row['doctor_last']}",
                        'doctor_initials': f"{row['doctor_first'][0]}{row['doctor_last'][0]}",
                        'specialization': row['specialization'] or 'General Dentistry',
                        'room': row['room'] or 'TBD',
                        'assists': []
                    }

                # Calculate age
                age = None
                if row['dob']:
                    today_date = datetime.now().date()
                    age = today_date.year - \
                        row['dob'].year - ((today_date.month, today_date.day)
                                           < (row['dob'].month, row['dob'].day))

                # Determine status badge based on appointment status
                status_badge = get_status_badge(row['appointment_status'])
                procedure = procedures_map.get(
                    row['appointment_id'], 'Consultation')

                # Check if assist is completed
                is_completed = row['assist_status'] == 'completed'

                doctors_dict[doctor_id]['assists'].append({
                    'id': row['appointment_id'],
                    'assist_id': row['assist_id'],
                    'patient_id': row['patient_id'],
                    'patient_name': f"{row['patient_first']} {row['patient_last']}",
                    'patient_initials': f"{row['patient_first'][0]}{row['patient_last'][0]}",
                    'patient_age': age,
                    'patient_number': row['patient_number'],
                    'patient_phone': row['phone'],
                    'time': format_time(row['start_time']),
                    'end_time': format_time(row['end_time']),
                    'status': row['appointment_status'],
                    'status_badge': status_badge,
                    'procedure': procedure,
                    'room': row['room'] or 'TBD',
                    'type': row['type'],
                    'notes': row['assist_notes'],
                    'is_completed': is_completed
                })

            # Convert to list and sort
            assists = list(doctors_dict.values())
            for doctor in assists:
                doctor['assists'].sort(key=lambda x: x['time'])
                doctor['assist_count'] = len(doctor['assists'])

            # Calculate stats
            all_assists = []
            for row in results:
                all_assists.append(row)

            stats = {
                'total_assists': len([a for a in all_assists]),
                'completed_assists': len([a for a in all_assists if a['assist_status'] == 'completed']),
                'pending_assists': len([a for a in all_assists if a['assist_status'] != 'completed']),
                'unique_doctors': len(set([a['doctor_id'] for a in all_assists]))
            }

        db.close()
        return jsonify({
            'success': True,
            'assists': assists,
            'stats': stats
        }), 200

    except Exception as e:
        print(f"Get my assists error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch assists'}), 500


# =========================================
# Get Assist Details
# =========================================

@my_assists_bp.route('/<int:assist_id>', methods=['GET'])
@login_required
@nurse_required
def get_assist_details(assist_id):
    """Get details for a specific assist"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.status as appointment_status,
                    a.room,
                    a.type,
                    a.notes as appointment_notes,
                    d.id as doctor_id,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    d.specialization,
                    p.id as patient_id,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    p.patient_number,
                    p.phone,
                    p.email,
                    p.dob,
                    p.allergies,
                    p.chronic_conditions,
                    p.current_medications,
                    p.medical_alerts,
                    ass.id as assist_id,
                    ass.status as assist_status,
                    ass.notes as assist_notes
                FROM assists ass
                JOIN appointments a ON ass.appointment_id = a.id
                JOIN users d ON a.doctor_id = d.id
                JOIN patients p ON a.patient_id = p.id
                WHERE ass.id = ? AND ass.nurse_id = ?
            """, (assist_id, nurse_id))

            result = cursor.fetchone()

            if not result:
                return jsonify({'error': 'Assist not found'}), 404

            # Get procedures separately
            cursor.execute("""
                SELECT GROUP_CONCAT(s.name, ', ') as procedures
                FROM appointment_services ast
                JOIN services s ON ast.service_id = s.id
                WHERE ast.appointment_id = ?
            """, (result['appointment_id'],))
            proc_result = cursor.fetchone()
            procedures = proc_result['procedures'] if proc_result else 'Consultation'

            # Calculate age
            age = None
            if result['dob']:
                today = datetime.now().date()
                age = today.year - \
                    result['dob'].year - ((today.month, today.day)
                                          < (result['dob'].month, result['dob'].day))

            # Get vitals
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
            """, (result['patient_id'],))
            vitals = cursor.fetchone()

            assist_details = {
                'id': result['assist_id'],
                'appointment_id': result['appointment_id'],
                'patient': {
                    'id': result['patient_id'],
                    'name': f"{result['patient_first']} {result['patient_last']}",
                    'initials': f"{result['patient_first'][0]}{result['patient_last'][0]}",
                    'patient_number': result['patient_number'],
                    'age': age,
                    'phone': result['phone'],
                    'email': result['email'],
                    'allergies': result['allergies'],
                    'chronic_conditions': result['chronic_conditions'],
                    'current_medications': result['current_medications'],
                    'medical_alerts': result['medical_alerts']
                },
                'doctor': {
                    'id': result['doctor_id'],
                    'name': f"Dr. {result['doctor_first']} {result['doctor_last']}",
                    'specialization': result['specialization'] or 'General Dentistry'
                },
                'time': format_time(result['start_time']),
                'end_time': format_time(result['end_time']),
                'room': result['room'] or 'TBD',
                'procedure': procedures,
                'status': result['appointment_status'],
                'type': result['type'],
                'notes': result['assist_notes'],
                'appointment_notes': result['appointment_notes'],
                'is_completed': result['assist_status'] == 'completed',
                'vitals': {
                    'bp_systolic': vitals['bp_systolic'] if vitals else None,
                    'bp_diastolic': vitals['bp_diastolic'] if vitals else None,
                    'heart_rate': vitals['heart_rate'] if vitals else None,
                    'temperature': vitals['temperature'] if vitals else None,
                    'oxygen_saturation': vitals['oxygen_saturation'] if vitals else None
                }
            }

        db.close()
        return jsonify({'success': True, 'assist': assist_details}), 200

    except Exception as e:
        print(f"Get assist details error: {e}")
        return jsonify({'error': 'Failed to fetch assist details'}), 500


# =========================================
# Complete Assist (Mark as Completed)
# =========================================

@my_assists_bp.route('/<int:assist_id>/complete', methods=['PUT'])
@login_required
@nurse_required
def complete_assist(assist_id):
    """Mark an assist as completed"""
    try:
        data = request.get_json()
        notes = data.get('notes', '')

        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get appointment_id from assist
            cursor.execute("""
                SELECT appointment_id FROM assists WHERE id = ? AND nurse_id = ?
            """, (assist_id, nurse_id))
            assist = cursor.fetchone()

            if not assist:
                return jsonify({'error': 'Assist not found'}), 404

            # Update assist status to completed
            cursor.execute("""
                UPDATE assists 
                SET status = 'completed', notes = (IFNULL(notes, '') || '\n\n' || ?)
                WHERE id = ?
            """, (notes, assist_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_ASSIST', 'assists', ?, ?)
            """, (nurse_id, assist_id, json.dumps({'status': 'completed', 'notes': notes})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Assist completed successfully'
        }), 200

    except Exception as e:
        print(f"Complete assist error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to complete assist'}), 500


# =========================================
# Get Preparation Tasks from TASKS TABLE
# =========================================

@my_assists_bp.route('/tasks', methods=['GET'])
@login_required
@nurse_required
def get_preparation_tasks():
    """Get preparation tasks for the nurse from the tasks table"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        tasks = []

        with db.cursor() as cursor:
            # Get all pending tasks assigned to this nurse (not completed)
            cursor.execute("""
                SELECT 
                    id,
                    task_name,
                    description,
                    due_date,
                    priority,
                    status,
                    created_at,
                    notes as task_notes
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
            """, (nurse_id,))

            results = cursor.fetchall()

            print(f"Found {len(results)} tasks for nurse {nurse_id}")

            for row in results:
                # Format due time
                due_time = ""
                urgency = "secondary"
                urgency_text = "Pending"
                time_display = "No deadline"

                if row['due_date']:
                    # Convert due_date to datetime if it's a string
                    due_date = row['due_date']
                    if isinstance(due_date, str):
                        due_date = datetime.strptime(
                            due_date, '%Y-%m-%d %H:%M:%S')

                    due_time = format_time(due_date)
                    time_display = due_time

                    # Calculate urgency based on time until due
                    now = datetime.now()
                    minutes_until = (due_date - now).total_seconds() // 60

                    if minutes_until <= 30 and minutes_until > 0:
                        urgency = "warning"
                        urgency_text = f"In {int(minutes_until)} min"
                    elif minutes_until <= 60 and minutes_until > 0:
                        urgency = "info"
                        urgency_text = f"In {int(minutes_until)} min"
                    elif minutes_until > 60:
                        urgency = "secondary"
                        urgency_text = f"Due {due_time}"
                    elif minutes_until <= 0:
                        urgency = "danger"
                        urgency_text = "Overdue"
                else:
                    due_time = "No deadline"
                    time_display = "Pending"
                    urgency_text = "Pending"

                # Get location or room from description if available
                room = "N/A"
                if row['description']:
                    # Try to extract room from description
                    if 'Room' in row['description']:
                        room_match = re.search(
                            r'Room\s+(\d+)', row['description'])
                        if room_match:
                            room = f"Room {room_match.group(1)}"
                if room == "N/A" and 'Room' in row['task_name']:
                    room_match = re.search(r'Room\s+(\d+)', row['task_name'])
                    if room_match:
                        room = f"Room {room_match.group(1)}"

                # Generate instruments based on task name
                instruments = get_instruments_for_procedure(row['task_name'])

                tasks.append({
                    'id': row['id'],
                    'task_name': row['task_name'],
                    'description': row['description'] or '',
                    'patient_name': row['task_name'].split(' ')[0] if row['task_name'] else 'Task',
                    'time': time_display,
                    'room': room,
                    'procedure': row['task_name'],
                    'instruments': instruments,
                    'urgency': urgency,
                    'urgency_text': urgency_text,
                    'due_time': urgency_text,
                    'priority': row['priority'],
                    'notes': row['task_notes']
                })

        db.close()

        print(f"Returning {len(tasks)} tasks to frontend")
        return jsonify({'success': True, 'tasks': tasks}), 200

    except Exception as e:
        print(f"Get preparation tasks error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch tasks'}), 500


# =========================================
# Mark Task Complete
# =========================================

@my_assists_bp.route('/tasks/<int:task_id>/complete', methods=['PUT'])
@login_required
@nurse_required
def complete_preparation_task(task_id):
    """Mark a task as completed"""
    try:
        nurse_id = session.get('user_id')
        data = request.get_json()
        notes = data.get('notes', '')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if task exists and belongs to this nurse
            cursor.execute("""
                SELECT id FROM tasks WHERE id = ? AND assigned_to = ?
            """, (task_id, nurse_id))
            if not cursor.fetchone():
                return jsonify({'error': 'Task not found'}), 404

            # Update task status to completed
            cursor.execute("""
                UPDATE tasks 
                SET status = 'completed', 
                    completed_at = datetime('now'),
                    notes = (IFNULL(notes, '') || '\n\nCompleted: ' || ?)
                WHERE id = ?
            """, (notes, task_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_TASK', 'tasks', ?, ?)
            """, (nurse_id, task_id, json.dumps({'status': 'completed', 'notes': notes})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Task completed successfully'}), 200

    except Exception as e:
        print(f"Complete task error: {e}")
        return jsonify({'error': 'Failed to complete task'}), 500
