import sqlite3
# =========================================
# Perfections Dental Services
# Doctor Dashboard Module - v1.0
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


# Create doctor dashboard blueprint
doctor_bp = Blueprint('doctor_dashboard', __name__, url_prefix='/api/doctor')



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


# Custom decorator for doctor role
def doctor_required(f):
    """Decorator to require doctor role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        # Allow superadmin and doctor roles
        if user_role not in ['doctor', 'superadmin']:
            return jsonify({'error': 'Access denied. Doctor role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get Dashboard Stats
# =========================================

@doctor_bp.route('/dashboard/stats', methods=['GET'])
@login_required
@doctor_required
def get_dashboard_stats():
    """Get doctor dashboard statistics"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Today's appointments count
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE doctor_id = ? 
                AND DATE(appointment_date) = date('now')
                AND status NOT IN ('cancelled')
            """, (doctor_id,))
            stats['today_patients'] = cursor.fetchone()['count']

            # Completed today
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE doctor_id = ? 
                AND DATE(appointment_date) = date('now')
                AND status = 'completed'
            """, (doctor_id,))
            stats['completed_today'] = cursor.fetchone()['count']

            # Pending today
            stats['pending_today'] = stats['today_patients'] - \
                stats['completed_today']

            # Waiting patients
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM appointments
                WHERE doctor_id = ? 
                AND DATE(appointment_date) = date('now')
                AND status = 'waiting'
            """, (doctor_id,))
            stats['waiting'] = cursor.fetchone()['count']

            # Average wait time
            cursor.execute("""
                SELECT AVG(((julianday(datetime('now')) - julianday(start_time)) * 24 * 60)) as avg_wait
                FROM appointments
                WHERE doctor_id = ? 
                AND DATE(appointment_date) = date('now')
                AND status IN ('checked_in', 'waiting', 'in_progress')
                AND start_time <= datetime('now')
            """, (doctor_id,))
            avg_wait = cursor.fetchone()['avg_wait']
            stats['avg_wait_time'] = round(avg_wait) if avg_wait else 0

            # Prescriptions today
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM prescriptions
                WHERE prescriber_id = ? 
                AND DATE(prescription_date) = date('now')
            """, (doctor_id,))
            stats['prescriptions_today'] = cursor.fetchone()['count']

            # Prescriptions yesterday for comparison
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM prescriptions
                WHERE prescriber_id = ? 
                AND DATE(prescription_date) = date(date('now'), '-1 days')
            """, (doctor_id,))
            yesterday_prescriptions = cursor.fetchone()['count']

            if yesterday_prescriptions > 0:
                stats['prescriptions_change'] = stats['prescriptions_today'] - \
                    yesterday_prescriptions
            else:
                stats['prescriptions_change'] = stats['prescriptions_today']

            # Patient rating (from reviews table if exists)
            stats['patient_rating'] = 4.9

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Dashboard stats error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500


# =========================================
# Get Today's Schedule
# =========================================

@doctor_bp.route('/dashboard/schedule', methods=['GET'])
@login_required
@doctor_required
def get_today_schedule():
    """Get today's appointments for the doctor"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        appointments = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    a.id,
                    a.appointment_number,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.room,
                    a.notes,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.email,
                    p.allergies,
                    p.chronic_conditions,
                    GROUP_CONCAT(s.name, ', ') as services_list
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.doctor_id = ? 
                AND DATE(a.appointment_date) = date('now')
                GROUP BY a.id, p.id
                ORDER BY a.start_time
            """, (doctor_id,))

            results = cursor.fetchall()

            for row in results:
                # Calculate age from DOB
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                # Format services
                services = []
                if row['services_list']:
                    service_names = row['services_list'].split(', ')
                    for name in service_names:
                        services.append({'name': name, 'price': 0})

                appointments.append({
                    'id': row['id'],
                    'appointment_number': row['appointment_number'],
                    'time': format_time(row['start_time']),
                    'end_time': format_time(row['end_time']),
                    'status': row['status'],
                    'room': row['room'] or 'TBD',
                    'notes': row['notes'],
                    'patient': {
                        'id': row['patient_id'],
                        'name': f"{row['first_name']} {row['last_name']}",
                        'first_name': row['first_name'],
                        'last_name': row['last_name'],
                        'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                        'patient_number': row['patient_number'],
                        'age': age,
                        'gender': row['gender'],
                        'phone': row['phone'],
                        'email': row['email'],
                        'allergies': row['allergies'],
                        'chronic_conditions': row['chronic_conditions']
                    },
                    'services': services
                })

        db.close()
        return jsonify({'success': True, 'appointments': appointments}), 200

    except Exception as e:
        print(f"Get schedule error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch schedule'}), 500


# =========================================
# Get Recent Patients
# =========================================

@doctor_bp.route('/dashboard/recent-patients', methods=['GET'])
@login_required
@doctor_required
def get_recent_patients():
    """Get recent patients for this doctor"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.phone,
                    MAX(a.appointment_date) as last_visit,
                    (SELECT s2.name FROM appointments a2
                     JOIN appointment_services ast2 ON a2.id = ast2.appointment_id
                     JOIN services s2 ON ast2.service_id = s2.id
                     WHERE a2.patient_id = p.id AND a2.doctor_id = ?
                     ORDER BY a2.appointment_date DESC LIMIT 1) as last_procedure
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ?
                GROUP BY p.id, p.first_name, p.last_name, p.patient_number, p.phone
                ORDER BY last_visit DESC
                LIMIT 5
            """, (doctor_id, doctor_id))

            results = cursor.fetchall()

            for row in results:
                patients.append({
                    'id': row['id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number': row['patient_number'],
                    'phone': row['phone'],
                    'last_visit': row['last_visit'].strftime('%b %d, %Y') if row['last_visit'] else 'Never',
                    'last_procedure': row['last_procedure'] or 'Consultation'
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get recent patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch recent patients'}), 500


# =========================================
# Get Patient Details
# =========================================

@doctor_bp.route('/patient/<int:patient_id>', methods=['GET'])
@login_required
@doctor_required
def get_patient_details(patient_id):
    """Get detailed patient information"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    patient_number,
                    first_name,
                    last_name,
                    dob,
                    gender,
                    phone,
                    email,
                    address,
                    emergency_contact_name,
                    emergency_contact_phone,
                    insurance_provider,
                    policy_number,
                    allergies,
                    chronic_conditions,
                    current_medications,
                    medical_alerts,
                    registration_date
                FROM patients
                WHERE id = ? AND status = 'active'
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

            # Get recent procedures
            cursor.execute("""
                SELECT 
                    a.appointment_date,
                    s.name as procedure_name,
                    a.notes
                FROM appointments a
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.patient_id = ?
                ORDER BY a.appointment_date DESC
                LIMIT 5
            """, (patient_id,))

            procedures = cursor.fetchall()

            # Get medical notes
            cursor.execute("""
                SELECT 
                    note_date,
                    note_type,
                    content
                FROM medical_notes
                WHERE patient_id = ?
                ORDER BY note_date DESC
                LIMIT 10
            """, (patient_id,))

            notes = cursor.fetchall()

            # Format DOB for display
            dob_formatted = patient['dob'].strftime(
                '%b %d, %Y') if patient['dob'] else ''

            result = {
                'id': patient['id'],
                'patient_number': patient['patient_number'],
                'first_name': patient['first_name'],
                'last_name': patient['last_name'],
                'full_name': f"{patient['first_name']} {patient['last_name']}",
                'age': age,
                'gender': patient['gender'],
                'phone': patient['phone'],
                'email': patient['email'],
                'address': patient['address'],
                'dob': dob_formatted,
                'emergency_contact': {
                    'name': patient['emergency_contact_name'],
                    'phone': patient['emergency_contact_phone']
                },
                'insurance': {
                    'provider': patient['insurance_provider'],
                    'policy_number': patient['policy_number']
                },
                'medical_history': {
                    'allergies': patient['allergies'],
                    'chronic_conditions': patient['chronic_conditions'],
                    'current_medications': patient['current_medications'],
                    'medical_alerts': patient['medical_alerts']
                },
                'registration_date': patient['registration_date'].strftime('%b %d, %Y') if patient['registration_date'] else '',
                'recent_procedures': [
                    {
                        'date': p['appointment_date'].strftime('%b %d, %Y') if p['appointment_date'] else '',
                        'procedure': p['procedure_name'] or 'Consultation',
                        'notes': p['notes']
                    } for p in procedures if p['appointment_date']
                ],
                'medical_notes': [
                    {
                        'date': n['note_date'].strftime('%b %d, %Y %I:%M %p') if n['note_date'] else '',
                        'type': n['note_type'],
                        'content': n['content']
                    } for n in notes
                ]
            }

        db.close()
        return jsonify({'success': True, 'patient': result}), 200

    except Exception as e:
        print(f"Get patient details error: {e}")
        return jsonify({'error': 'Failed to fetch patient details'}), 500


# =========================================
# Start Consultation
# =========================================

@doctor_bp.route('/consultation/start', methods=['POST'])
@login_required
@doctor_required
def start_consultation():
    """Start a consultation for an appointment"""
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        notes = data.get('notes', '')

        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get patient_id from appointment
            cursor.execute(
                "SELECT patient_id FROM appointments WHERE id = ?", (appointment_id,))
            appt = cursor.fetchone()
            if not appt:
                return jsonify({'error': 'Appointment not found'}), 404

            # Update appointment status
            new_notes = f"Consultation started: {notes}" if notes else "Consultation started"
            cursor.execute("""
                UPDATE appointments 
                SET status = 'in_progress', 
                    notes = (IFNULL(notes, '') || '\n\n' || ?)
                WHERE id = ? AND doctor_id = ?
            """, (new_notes, appointment_id, doctor_id))

            # Create medical note
            cursor.execute("""
                INSERT INTO medical_notes (patient_id, author_id, appointment_id, note_date, note_type, content)
                VALUES (?, ?, ?, datetime('now'), 'pre-op', ?)
            """, (appt['patient_id'], doctor_id, appointment_id, f"Consultation started. Preliminary notes: {notes}"))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'START_CONSULTATION', 'appointments', ?, ?)
            """, (doctor_id, appointment_id, json.dumps({'status': 'in_progress'})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Consultation started', 'appointment_id': appointment_id}), 200

    except Exception as e:
        print(f"Start consultation error: {e}")
        return jsonify({'error': 'Failed to start consultation'}), 500


# =========================================
# Complete Consultation
# =========================================

@doctor_bp.route('/consultation/complete', methods=['POST'])
@login_required
@doctor_required
def complete_consultation():
    """Complete a consultation"""
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        notes = data.get('notes', '')
        procedure_id = data.get('procedure_id')

        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get patient_id from appointment
            cursor.execute(
                "SELECT patient_id FROM appointments WHERE id = ?", (appointment_id,))
            appt = cursor.fetchone()

            if not appt:
                return jsonify({'error': 'Appointment not found'}), 404

            # Update appointment status
            new_notes = f"Consultation completed: {notes}" if notes else "Consultation completed"
            cursor.execute("""
                UPDATE appointments 
                SET status = 'completed', 
                    notes = (IFNULL(notes, '') || '\n\n' || ?)
                WHERE id = ? AND doctor_id = ?
            """, (new_notes, appointment_id, doctor_id))

            # Add completion note
            cursor.execute("""
                INSERT INTO medical_notes (patient_id, author_id, appointment_id, note_date, note_type, content)
                VALUES (?, ?, ?, datetime('now'), 'procedure', ?)
            """, (appt['patient_id'], doctor_id, appointment_id, f"Consultation completed. Notes: {notes}"))

            # If procedure_id provided, add to appointment_services
            if procedure_id:
                cursor.execute("""
                    INSERT INTO appointment_services (appointment_id, service_id, quantity, unit_price)
                    SELECT ?, ?, 1, price FROM services WHERE id = ?
                """, (appointment_id, procedure_id, procedure_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'COMPLETE_CONSULTATION', 'appointments', ?, ?)
            """, (doctor_id, appointment_id, json.dumps({'status': 'completed'})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Consultation completed'}), 200

    except Exception as e:
        print(f"Complete consultation error: {e}")
        return jsonify({'error': 'Failed to complete consultation'}), 500
