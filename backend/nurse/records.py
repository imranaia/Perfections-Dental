import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Records Module - v1.0
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


# Create nurse records blueprint
nurse_records_bp = Blueprint(
    'nurse_records', __name__, url_prefix='/api/nurse/records')



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
# Get Clinic Info
# =========================================

@nurse_records_bp.route('/clinic-info', methods=['GET'])
@login_required
@nurse_required
def get_clinic_info():
    """Get clinic information from settings"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        clinic_info = {}

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT setting_key, setting_value FROM clinic_settings")
            settings = cursor.fetchall()
            for setting in settings:
                clinic_info[setting['setting_key']] = setting['setting_value']

        db.close()
        return jsonify({'success': True, 'clinic_info': clinic_info}), 200

    except Exception as e:
        print(f"Get clinic info error: {e}")
        return jsonify({'error': 'Failed to fetch clinic info'}), 500


# =========================================
# Search Patients
# =========================================

@nurse_records_bp.route('/search', methods=['GET'])
@login_required
@nurse_required
def search_patients():
    """Search patients by name, ID, or phone"""
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
                SELECT 
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.email,
                    (SELECT MAX(appointment_date) FROM appointments WHERE patient_id = p.id) as last_visit
                FROM patients p
                WHERE p.status = 'active'
                AND (p.first_name LIKE ? OR p.last_name LIKE ? OR p.patient_number LIKE ? OR p.phone LIKE ?)
                LIMIT 10
            """, (search_term, search_term, search_term, search_term))

            results = cursor.fetchall()

            for row in results:
                # Calculate age
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                patients.append({
                    'id': row['id'],
                    'patient_number': row['patient_number'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'full_name': f"{row['first_name']} {row['last_name']}",
                    'age': age,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'last_visit': row['last_visit'].strftime('%b %d, %Y') if row['last_visit'] else 'Never'
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Search patients error: {e}")
        return jsonify({'error': 'Failed to search patients'}), 500


# =========================================
# Get Patient Details with All Visits
# =========================================

@nurse_records_bp.route('/<int:patient_id>', methods=['GET'])
@login_required
@nurse_required
def get_patient_records(patient_id):
    """Get complete patient records with all visits"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get patient details
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
            vitals = cursor.fetchone() or {}

            # Get all visits (appointments with medical notes)
            cursor.execute("""
                SELECT 
                    a.id as appointment_id,
                    a.appointment_date,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.room,
                    a.type,
                    GROUP_CONCAT(s.name, ', ') as procedures,
                    mn.id as note_id,
                    mn.note_date,
                    mn.note_type,
                    mn.content as notes_content,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    d.specialization as doctor_specialization,
                    GROUP_CONCAT((nurses.first_name || ' ' || nurses.last_name), ', ') as nurse_names
                FROM appointments a
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                LEFT JOIN medical_notes mn ON a.id = mn.appointment_id
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN assists ass ON a.id = ass.appointment_id
                LEFT JOIN users nurses ON ass.nurse_id = nurses.id
                WHERE a.patient_id = ?
                GROUP BY a.id, mn.id
                ORDER BY a.appointment_date DESC, a.start_time DESC
            """, (patient_id,))

            visits_raw = cursor.fetchall()

            # Process visits
            visits = []
            for v in visits_raw:
                visits.append({
                    'id': v['appointment_id'],
                    'note_id': v['note_id'],
                    'date': v['appointment_date'].strftime('%b %d, %Y') if v['appointment_date'] else '',
                    'date_raw': v['appointment_date'].strftime('%Y-%m-%d') if v['appointment_date'] else '',
                    'start_time': format_time(v['start_time']),
                    'end_time': format_time(v['end_time']),
                    'status': v['status'],
                    'room': v['room'],
                    'type': v['type'],
                    'procedures': v['procedures'] or 'Consultation',
                    'notes_content': v['notes_content'] or '',
                    'note_type': v['note_type'],
                    'note_date': v['note_date'].strftime('%b %d, %Y %I:%M %p') if v['note_date'] else '',
                    'doctor_name': f"Dr. {v['doctor_first']} {v['doctor_last']}" if v['doctor_first'] else 'Not assigned',
                    'doctor_specialization': v['doctor_specialization'] or 'General Dentistry',
                    'nurse_names': v['nurse_names'] or 'None assigned'
                })

            # Parse medical history lists
            allergies_list = []
            if patient['allergies']:
                allergies_list = [a.strip()
                                  for a in patient['allergies'].split(',')]

            conditions_list = []
            if patient['chronic_conditions']:
                conditions_list = [c.strip()
                                   for c in patient['chronic_conditions'].split(',')]

            medications_list = []
            if patient['current_medications']:
                medications_list = [
                    m.strip() for m in patient['current_medications'].split(',')]

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
                'address': patient['address'],
                'dob': patient['dob'].strftime('%b %d, %Y') if patient['dob'] else '',
                'registration_date': patient['registration_date'].strftime('%b %d, %Y') if patient['registration_date'] else '',
                'emergency_contact': {
                    'name': patient['emergency_contact_name'],
                    'phone': patient['emergency_contact_phone']
                },
                'insurance': {
                    'provider': patient['insurance_provider'],
                    'policy_number': patient['policy_number']
                },
                'allergies_list': allergies_list,
                'conditions_list': conditions_list,
                'medications_list': medications_list,
                'vitals': {
                    'bp_systolic': vitals.get('bp_systolic'),
                    'bp_diastolic': vitals.get('bp_diastolic'),
                    'heart_rate': vitals.get('heart_rate'),
                    'temperature': vitals.get('temperature'),
                    'oxygen_saturation': vitals.get('oxygen_saturation'),
                    'recorded_at': vitals['recorded_at'].strftime('%b %d, %Y %I:%M %p') if vitals.get('recorded_at') else ''
                },
                'visits': visits
            }

        db.close()
        return jsonify({'success': True, 'patient': result}), 200

    except Exception as e:
        print(f"Get patient records error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patient records'}), 500


# =========================================
# Get Single Visit Details
# =========================================

@nurse_records_bp.route('/visit/<int:appointment_id>', methods=['GET'])
@login_required
@nurse_required
def get_visit_details(appointment_id):
    """Get detailed information for a specific visit"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    a.id as appointment_id,
                    a.appointment_date,
                    a.start_time,
                    a.end_time,
                    a.status,
                    a.room,
                    a.type,
                    a.notes as appointment_notes,
                    GROUP_CONCAT(s.name, ', ') as procedures,
                    mn.id as note_id,
                    mn.note_date,
                    mn.note_type,
                    mn.content as notes_content,
                    p.id as patient_id,
                    p.first_name,
                    p.last_name,
                    p.patient_number,
                    p.dob,
                    p.gender,
                    p.phone,
                    p.email,
                    p.address,
                    p.allergies,
                    p.chronic_conditions,
                    p.current_medications,
                    p.medical_alerts,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    d.specialization as doctor_specialization,
                    GROUP_CONCAT((nurses.first_name || ' ' || nurses.last_name), ', ') as nurse_names
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                LEFT JOIN medical_notes mn ON a.id = mn.appointment_id
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN assists ass ON a.id = ass.appointment_id
                LEFT JOIN users nurses ON ass.nurse_id = nurses.id
                WHERE a.id = ?
                GROUP BY a.id, mn.id
            """, (appointment_id,))

            row = cursor.fetchone()

            if not row:
                return jsonify({'error': 'Visit not found'}), 404

            # Calculate age
            age = None
            if row['dob']:
                today = datetime.now().date()
                age = today.year - \
                    row['dob'].year - ((today.month, today.day)
                                       < (row['dob'].month, row['dob'].day))

            # Get vitals for this appointment
            cursor.execute("""
                SELECT 
                    bp_systolic,
                    bp_diastolic,
                    heart_rate,
                    temperature,
                    oxygen_saturation,
                    recorded_at
                FROM vitals
                WHERE appointment_id = ?
                ORDER BY recorded_at DESC
                LIMIT 1
            """, (appointment_id,))
            vitals = cursor.fetchone() or {}

            visit = {
                'id': row['appointment_id'],
                'note_id': row['note_id'],
                'date': row['appointment_date'].strftime('%b %d, %Y') if row['appointment_date'] else '',
                'date_raw': row['appointment_date'].strftime('%Y-%m-%d') if row['appointment_date'] else '',
                'start_time': format_time(row['start_time']),
                'end_time': format_time(row['end_time']),
                'status': row['status'],
                'room': row['room'],
                'type': row['type'],
                'procedures': row['procedures'] or 'Consultation',
                'notes_content': row['notes_content'] or '',
                'note_type': row['note_type'],
                'note_date': row['note_date'].strftime('%b %d, %Y %I:%M %p') if row['note_date'] else '',
                'doctor_name': f"Dr. {row['doctor_first']} {row['doctor_last']}" if row['doctor_first'] else 'Not assigned',
                'doctor_specialization': row['doctor_specialization'] or 'General Dentistry',
                'nurse_names': row['nurse_names'] or 'None assigned',
                'patient': {
                    'id': row['patient_id'],
                    'full_name': f"{row['first_name']} {row['last_name']}",
                    'patient_number': row['patient_number'],
                    'age': age,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'email': row['email'],
                    'dob': row['dob'].strftime('%b %d, %Y') if row['dob'] else '',
                    'address': row['address']
                },
                'vitals': {
                    'bp_systolic': vitals.get('bp_systolic'),
                    'bp_diastolic': vitals.get('bp_diastolic'),
                    'heart_rate': vitals.get('heart_rate'),
                    'temperature': vitals.get('temperature'),
                    'oxygen_saturation': vitals.get('oxygen_saturation'),
                    'recorded_at': vitals['recorded_at'].strftime('%b %d, %Y %I:%M %p') if vitals.get('recorded_at') else ''
                }
            }

        db.close()
        return jsonify({'success': True, 'visit': visit}), 200

    except Exception as e:
        print(f"Get visit details error: {e}")
        return jsonify({'error': 'Failed to fetch visit details'}), 500
