import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Procedures Module - v1.0
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


# Create procedures blueprint
procedures_bp = Blueprint('nurse_procedures', __name__,
                          url_prefix='/api/nurse/procedures')



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
# Get All Nurse Procedures (from actual appointments)
# =========================================

@procedures_bp.route('/', methods=['GET'])
@login_required
@nurse_required
def get_procedures():
    """Get all nurse procedures from actual appointments"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        procedures = []
        stats = {
            'today_count': 0,
            'completed_today': 0,
            'week_count': 0,
            'upcoming_count': 0
        }

        with db.cursor() as cursor:
            # Get all nurse-only appointments for this nurse
            cursor.execute("""
                SELECT 
                    a.id,
                    a.appointment_number,
                    a.appointment_date,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.room,
                    a.notes,
                    a.type,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    p.medical_alerts,
                    s.id as service_id,
                    s.name as service_name,
                    s.duration_minutes,
                    s.price,
                    s.description as service_description
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.nurse_id = ? 
                AND a.type = 'nurse_only'
                AND a.status NOT IN ('cancelled')
                ORDER BY a.appointment_date DESC, a.start_time DESC
            """, (nurse_id,))

            results = cursor.fetchall()

            # Group by service name to show unique procedures
            procedures_map = {}
            today = datetime.now().date()

            for row in results:
                service_name = row['service_name'] or 'Nurse Procedure'
                # Use appointment ID as fallback
                service_id = row['service_id'] or row['id']

                if service_name not in procedures_map:
                    procedures_map[service_name] = {
                        'id': service_id,
                        'name': service_name,
                        'duration': row['duration_minutes'] or 30,
                        'price': float(row['price']) if row['price'] else 0,
                        'description': row['service_description'] or '',
                        'scheduled': [],
                        'scheduled_count': 0,
                        'today_count': 0,
                        'is_eligible': True,
                        'is_emergency': False
                    }

                # Check if this appointment is today
                appointment_date = row['appointment_date']
                is_today = appointment_date == today if appointment_date else False

                appointment_info = {
                    'id': row['id'],
                    'patient_id': row['patient_id'],
                    'patient_name': f"{row['first_name']} {row['last_name']}",
                    'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number': row['patient_number'],
                    'time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'is_today': is_today,
                    'has_allergies': bool(row['allergies']),
                    'has_alerts': bool(row['medical_alerts'])
                }

                procedures_map[service_name]['scheduled'].append(
                    appointment_info)
                procedures_map[service_name]['scheduled_count'] += 1

                if is_today:
                    procedures_map[service_name]['today_count'] += 1
                    stats['today_count'] += 1
                    if row['status'] == 'completed':
                        stats['completed_today'] += 1
                    elif row['status'] in ['scheduled', 'in_progress']:
                        stats['upcoming_count'] += 1

            # Get week count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments a
                WHERE a.nurse_id = ? 
                AND a.type = 'nurse_only'
                AND CAST(strftime('%W', a.appointment_date) AS INTEGER) = CAST(strftime('%W', date('now')) AS INTEGER)
                AND a.status NOT IN ('cancelled')
            """, (nurse_id,))
            stats['week_count'] = cursor.fetchone()['count']

            # Convert map to list
            procedures = list(procedures_map.values())

            # Sort by today's count first, then by name
            procedures.sort(key=lambda x: (-x['today_count'], x['name']))

        db.close()
        return jsonify({'success': True, 'procedures': procedures, 'stats': stats}), 200

    except Exception as e:
        print(f"Get procedures error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch procedures'}), 500


# =========================================
# Get Today's Schedule (Nurse-Only Appointments)
# =========================================

@procedures_bp.route('/schedule', methods=['GET'])
@login_required
@nurse_required
def get_today_schedule():
    """Get today's scheduled nurse-only procedures"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        schedule = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    a.id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.notes,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    p.medical_alerts,
                    s.name as procedure_name,
                    s.duration_minutes
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.nurse_id = ? 
                AND DATE(a.appointment_date) = date('now')
                AND a.type = 'nurse_only'
                AND a.status NOT IN ('cancelled')
                ORDER BY a.start_time
            """, (nurse_id,))

            results = cursor.fetchall()

            for row in results:
                schedule.append({
                    'id': row['id'],
                    'time': format_time(row['start_time']),
                    'end_time': format_time(row['end_time']),
                    'patient_name': f"{row['first_name']} {row['last_name']}",
                    'patient_id': row['patient_id'],
                    'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'procedure': row['procedure_name'] or 'Nurse Procedure',
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'duration': row['duration_minutes'] or 30,
                    'has_allergies': bool(row['allergies']),
                    'has_alerts': bool(row['medical_alerts'])
                })

        db.close()
        return jsonify({'success': True, 'schedule': schedule}), 200

    except Exception as e:
        print(f"Get schedule error: {e}")
        return jsonify({'error': 'Failed to fetch schedule'}), 500


# =========================================
# Get Procedure Details (by appointment ID)
# =========================================

@procedures_bp.route('/appointment/<int:appointment_id>', methods=['GET'])
@login_required
@nurse_required
def get_procedure_by_appointment(appointment_id):
    """Get procedure details for a specific appointment"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    a.id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.notes,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.allergies,
                    p.medical_alerts,
                    s.id as service_id,
                    s.name as procedure_name,
                    s.duration_minutes,
                    s.price,
                    s.description
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.id = ? AND a.nurse_id = ? AND a.type = 'nurse_only'
            """, (appointment_id, nurse_id))

            row = cursor.fetchone()

            if not row:
                return jsonify({'error': 'Appointment not found'}), 404

            # Define steps based on procedure name
            procedure_name = row['procedure_name'] or 'Nurse Procedure'
            steps = get_procedure_steps(procedure_name)

            result = {
                'id': row['id'],
                'appointment_id': row['id'],
                'name': procedure_name,
                'category': 'Nurse Procedure',
                'duration': row['duration_minutes'] or 30,
                'price': float(row['price']) if row['price'] else 0,
                'description': row['description'] or '',
                'steps': steps,
                'patient': {
                    'id': row['patient_id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'patient_number': row['patient_number'],
                    'age': calculate_age(row['dob']) if row['dob'] else None,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'allergies': row['allergies'],
                    'medical_alerts': row['medical_alerts']
                },
                'appointment': {
                    'time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'notes': row['notes']
                }
            }

        db.close()
        return jsonify({'success': True, 'procedure': result}), 200

    except Exception as e:
        print(f"Get procedure by appointment error: {e}")
        return jsonify({'error': 'Failed to fetch procedure details'}), 500


# =========================================
# Get Patients for Scheduling
# =========================================

@procedures_bp.route('/patients', methods=['GET'])
@login_required
@nurse_required
def get_patients():
    """Get patients for scheduling a nurse procedure"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    patient_number,
                    first_name,
                    last_name,
                    phone,
                    email
                FROM patients
                WHERE status = 'active'
                ORDER BY last_name, first_name
                LIMIT 50
            """)
            results = cursor.fetchall()

            for row in results:
                patients.append({
                    'id': row['id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'patient_number': row['patient_number'],
                    'phone': row['phone'],
                    'email': row['email']
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get patients error: {e}")
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Available Time Slots
# =========================================

@procedures_bp.route('/timeslots', methods=['GET'])
@login_required
@nurse_required
def get_time_slots():
    """Get available time slots for scheduling"""
    try:
        # Business hours: 9 AM to 5 PM, 30-minute slots
        slots = []
        for hour in range(9, 17):
            for minute in [0, 30]:
                if hour == 17 and minute == 30:
                    continue
                time_str = f"{hour:02d}:{minute:02d}"
                slots.append({
                    'value': time_str,
                    'label': datetime.strptime(time_str, '%H:%M').strftime('%I:%M %p')
                })

        return jsonify({'success': True, 'slots': slots}), 200

    except Exception as e:
        print(f"Get time slots error: {e}")
        return jsonify({'error': 'Failed to fetch time slots'}), 500


# =========================================
# Schedule a Nurse-Only Procedure
# =========================================

@procedures_bp.route('/schedule', methods=['POST'])
@login_required
@nurse_required
def schedule_procedure():
    """Schedule a new nurse-only procedure"""
    try:
        data = request.get_json()
        nurse_id = session.get('user_id')

        patient_id = data.get('patient_id')
        procedure_name = data.get('procedure_name')
        appointment_date = data.get('appointment_date')
        start_time = data.get('start_time')
        room = data.get('room', 'Room 1')
        notes = data.get('notes', '')

        if not patient_id or not appointment_date or not start_time:
            return jsonify({'error': 'Missing required fields'}), 400

        # Generate appointment number
        import random
        appointment_number = f"NURSE-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

        # Calculate end time (default 30 minutes)
        start_dt = datetime.strptime(start_time, '%H:%M')
        end_dt = start_dt + timedelta(minutes=30)
        end_time = end_dt.strftime('%H:%M:%S')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Create the appointment
            cursor.execute("""
                INSERT INTO appointments (
                    appointment_number, 
                    patient_id, 
                    nurse_id, 
                    appointment_date, 
                    start_time, 
                    end_time, 
                    status, 
                    type, 
                    room, 
                    notes, 
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, 'scheduled', 'nurse_only', ?, ?, ?)
            """, (appointment_number, patient_id, nurse_id, appointment_date, start_time, end_time, room, notes, nurse_id))

            appointment_id = cursor.lastrowid

            # Log the action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'SCHEDULE_NURSE_PROCEDURE', 'appointments', ?, ?)
            """, (nurse_id, appointment_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Procedure scheduled successfully',
            'appointment_id': appointment_id,
            'appointment_number': appointment_number
        }), 201

    except Exception as e:
        print(f"Schedule procedure error: {e}")
        return jsonify({'error': 'Failed to schedule procedure'}), 500


# =========================================
# Start Procedure (Update Appointment Status)
# =========================================

@procedures_bp.route('/appointment/<int:appointment_id>/start', methods=['PUT'])
@login_required
@nurse_required
def start_procedure(appointment_id):
    """Start a procedure by updating appointment status"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Verify appointment belongs to this nurse and is nurse_only
            cursor.execute("""
                SELECT id, patient_id FROM appointments 
                WHERE id = ? AND nurse_id = ? AND type = 'nurse_only'
            """, (appointment_id, nurse_id))

            if not cursor.fetchone():
                return jsonify({'error': 'Appointment not found'}), 404

            # Update appointment status
            cursor.execute("""
                UPDATE appointments 
                SET status = 'in_progress', updated_at = datetime('now')
                WHERE id = ?
            """, (appointment_id,))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'START_NURSE_PROCEDURE', 'appointments', ?, ?)
            """, (nurse_id, appointment_id, json.dumps({'status': 'in_progress'})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Procedure started successfully'}), 200

    except Exception as e:
        print(f"Start procedure error: {e}")
        return jsonify({'error': 'Failed to start procedure'}), 500


# =========================================
# Complete Procedure
# =========================================

@procedures_bp.route('/appointment/<int:appointment_id>/complete', methods=['PUT'])
@login_required
@nurse_required
def complete_procedure(appointment_id):
    """Complete a procedure"""
    try:
        nurse_id = session.get('user_id')
        data = request.get_json()
        notes = data.get('notes', '')
        steps_completed = data.get('steps_completed', [])

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get appointment details
            cursor.execute("""
                SELECT id, patient_id FROM appointments 
                WHERE id = ? AND nurse_id = ? AND type = 'nurse_only'
            """, (appointment_id, nurse_id))
            appointment = cursor.fetchone()

            if not appointment:
                return jsonify({'error': 'Appointment not found'}), 404

            # Update appointment status
            cursor.execute("""
                UPDATE appointments 
                SET status = 'completed', updated_at = datetime('now')
                WHERE id = ?
            """, (appointment_id,))

            # Create medical note
            note_content = f"""=== NURSE PROCEDURE COMPLETED ===
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Nurse: {session.get('name', 'Nurse')}

=== STEPS COMPLETED ===
{chr(10).join([f'✓ {step}' for step in steps_completed]) if steps_completed else 'Procedure completed successfully'}

=== NOTES ===
{notes if notes else 'No additional notes'}

=== STATUS ===
Completed by nursing staff"""

            cursor.execute("""
                INSERT INTO medical_notes (patient_id, author_id, appointment_id, note_date, note_type, content)
                VALUES (?, ?, ?, datetime('now'), 'procedure', ?)
            """, (appointment['patient_id'], nurse_id, appointment_id, note_content))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_NURSE_PROCEDURE', 'appointments', ?, ?)
            """, (nurse_id, appointment_id, json.dumps({'status': 'completed'})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Procedure completed successfully'}), 200

    except Exception as e:
        print(f"Complete procedure error: {e}")
        return jsonify({'error': 'Failed to complete procedure'}), 500


# =========================================
# Helper Functions
# =========================================

def calculate_age(dob):
    """Calculate age from date of birth"""
    if not dob:
        return None
    today = datetime.now().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def get_procedure_steps(procedure_name):
    """Get standard steps for a procedure"""
    steps = {
        'Teeth Cleaning': [
            'Prepare cleaning instruments (scaler, polish, suction)',
            'Check patient vitals and medical history',
            'Perform scaling to remove plaque and tartar',
            'Polish teeth with prophy paste',
            'Apply fluoride treatment (if indicated)',
            'Provide post-procedure instructions',
            'Document procedure in patient chart'
        ],
        'Fluoride Treatment': [
            'Prepare fluoride tray and materials',
            'Dry teeth thoroughly',
            'Apply fluoride varnish or gel',
            'Set timer for 4 minutes',
            'Remove excess fluoride',
            'Instruct patient not to eat/drink for 30 minutes',
            'Document treatment'
        ],
        'Dental Sealants': [
            'Clean and dry tooth surface',
            'Apply etch solution',
            'Rinse and dry thoroughly',
            'Apply sealant material',
            'Cure with light',
            'Check occlusion and adjust if needed',
            'Document placement'
        ],
        'Oral Hygiene Instruction': [
            'Assess current oral hygiene practices',
            'Demonstrate proper brushing technique',
            'Demonstrate proper flossing technique',
            'Discuss importance of regular dental visits',
            'Provide educational materials',
            'Answer patient questions',
            'Document instruction provided'
        ]
    }

    # Default steps for any procedure
    default_steps = [
        'Prepare necessary instruments and materials',
        'Verify patient identity',
        'Check patient vitals and allergies',
        'Explain procedure to patient',
        'Perform procedure according to protocol',
        'Document procedure details',
        'Provide post-procedure instructions'
    ]

    for key in steps:
        if key in procedure_name:
            return steps[key]
    return default_steps
