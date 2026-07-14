import sqlite3
# =========================================
# Perfections Dental Services
# Doctor My Patients Module - v1.0
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


# Create my patients blueprint
my_patients_bp = Blueprint('my_patients', __name__,
                           url_prefix='/api/doctor/patients')



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


def doctor_required(f):
    """Decorator to require doctor role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['doctor', 'superadmin']:
            return jsonify({'error': 'Access denied. Doctor role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


# =========================================
# Get My Patients
# =========================================

@my_patients_bp.route('/', methods=['GET'])
@login_required
@doctor_required
def get_my_patients():
    """Get all patients for the logged-in doctor"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Get query parameters for filtering
        search = request.args.get('search', '')
        status_filter = request.args.get('status', 'all')
        sort_by = request.args.get('sort', 'recent')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        patients = []

        with db.cursor() as cursor:
            # Build query
            query = """
                SELECT DISTINCT
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
                    p.medical_alerts,
                    p.registration_date,
                    p.status as patient_status,
                    MAX(a.appointment_date) as last_visit,
                    (SELECT appointment_date FROM appointments WHERE patient_id = p.id AND doctor_id = ? AND appointment_date >= date('now') AND status NOT IN ('completed', 'cancelled') ORDER BY appointment_date ASC, start_time ASC LIMIT 1) as next_appointment_date,
                    (SELECT start_time FROM appointments WHERE patient_id = p.id AND doctor_id = ? AND appointment_date >= date('now') AND status NOT IN ('completed', 'cancelled') ORDER BY appointment_date ASC, start_time ASC LIMIT 1) as next_appointment_time,
                    (SELECT id FROM appointments WHERE patient_id = p.id AND doctor_id = ? AND appointment_date >= date('now') AND status NOT IN ('completed', 'cancelled') ORDER BY appointment_date ASC, start_time ASC LIMIT 1) as next_appointment_id,
                    (SELECT GROUP_CONCAT(s.name, ', ') FROM appointment_services ast JOIN services s ON ast.service_id = s.id JOIN appointments a ON ast.appointment_id = a.id WHERE a.patient_id = p.id AND a.doctor_id = ? AND a.status NOT IN ('completed', 'cancelled')) as treatments,
                    (SELECT status FROM appointments WHERE patient_id = p.id AND doctor_id = ? AND appointment_date = date('now') ORDER BY start_time ASC LIMIT 1) as today_status
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ?
                AND p.status = 'active'
            """
            params = [doctor_id, doctor_id, doctor_id,
                      doctor_id, doctor_id, doctor_id]

            # Add search filter
            if search:
                query += """ AND (
                    p.first_name LIKE ? OR 
                    p.last_name LIKE ? OR 
                    p.patient_number LIKE ? OR 
                    p.phone LIKE ? OR
                    (p.first_name || ' ' || p.last_name) LIKE ?
                )"""
                search_term = f"%{search}%"
                params.extend([search_term, search_term,
                              search_term, search_term, search_term])

            # Add status filter - EXCLUDE completed appointments from appointments filter
            if status_filter == 'active':
                query += " AND a.status NOT IN ('cancelled', 'completed')"
            elif status_filter == 'appointments':
                query += " AND a.appointment_date = date('now') AND a.status NOT IN ('completed', 'cancelled')"
            elif status_filter == 'followup':
                query += " AND a.status = 'waiting'"
            elif status_filter == 'new':
                query += " AND p.registration_date >= date(date('now'), '-30 days')"

            # Add GROUP BY
            query += " GROUP BY p.id, p.patient_number, p.first_name, p.last_name, p.dob, p.gender, p.phone, p.email, p.allergies, p.chronic_conditions, p.current_medications, p.medical_alerts, p.registration_date, p.status"

            # Add sorting
            if sort_by == 'name':
                query += " ORDER BY p.last_name, p.first_name"
            elif sort_by == 'oldest':
                query += " ORDER BY p.registration_date ASC"
            elif sort_by == 'time':
                query += " ORDER BY next_appointment_time ASC"
            else:  # recent
                query += " ORDER BY COALESCE(last_visit, '1900-01-01') DESC"

            # Add pagination
            offset = (page - 1) * per_page
            query += " LIMIT ? OFFSET ?"
            params.extend([per_page, offset])

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            # Get total count for pagination
            count_query = """
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ? AND p.status = 'active'
            """
            count_params = [doctor_id]

            if search:
                count_query += """ AND (
                    p.first_name LIKE ? OR 
                    p.last_name LIKE ? OR 
                    p.patient_number LIKE ? OR 
                    p.phone LIKE ? OR
                    (p.first_name || ' ' || p.last_name) LIKE ?
                )"""
                count_params.extend(
                    [search_term, search_term, search_term, search_term, search_term])

            cursor.execute(count_query, tuple(count_params))
            total_count = cursor.fetchone()['total']

            for row in results:
                # Calculate age
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                # Determine status badge
                today_status = row['today_status']
                if today_status == 'checked_in':
                    status_badge = {'text': 'In Clinic',
                                    'icon': 'fa-circle', 'color': 'success'}
                elif today_status == 'waiting':
                    status_badge = {'text': 'Waiting',
                                    'icon': 'fa-circle', 'color': 'warning'}
                elif today_status == 'in_progress':
                    status_badge = {'text': 'In Progress',
                                    'icon': 'fa-play-circle', 'color': 'info'}
                elif row['next_appointment_date'] and row['next_appointment_date'] == datetime.now().date():
                    status_badge = {'text': 'Today',
                                    'icon': 'fa-calendar-check', 'color': 'info'}
                elif row['registration_date'] and (datetime.now().date() - row['registration_date']).days <= 30:
                    status_badge = {'text': 'New Patient',
                                    'icon': 'fa-user-plus', 'color': 'success'}
                else:
                    status_badge = {'text': 'Active',
                                    'icon': 'fa-user-check', 'color': 'info'}

                # Format next appointment
                next_appointment = None
                if row['next_appointment_date']:
                    next_appointment = {
                        'id': row['next_appointment_id'],
                        'date': row['next_appointment_date'].strftime('%b %d, %Y') if row['next_appointment_date'] else '',
                        'time': format_time(row['next_appointment_time']) if row['next_appointment_time'] else ''
                    }

                # Format treatments list
                treatments = []
                if row['treatments']:
                    treatments = [t.strip()
                                  for t in row['treatments'].split(',')]

                # Check for medical alerts
                medical_alerts = []
                if row['allergies']:
                    medical_alerts.append(
                        {'type': 'allergy', 'text': row['allergies']})
                if row['chronic_conditions']:
                    medical_alerts.append(
                        {'type': 'condition', 'text': row['chronic_conditions']})
                if row['medical_alerts']:
                    medical_alerts.append(
                        {'type': 'alert', 'text': row['medical_alerts']})

                patients.append({
                    'id': row['id'],
                    'patient_number': row['patient_number'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'full_name': f"{row['first_name']} {row['last_name']}",
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'age': age,
                    'gender': row['gender'],
                    'phone': row['phone'],
                    'email': row['email'],
                    'last_visit': row['last_visit'].strftime('%b %d, %Y') if row['last_visit'] else 'Never',
                    'next_appointment': next_appointment,
                    'next_appointment_id': row['next_appointment_id'],
                    'treatments': treatments[:3],
                    'medical_alerts': medical_alerts,
                    'status_badge': status_badge,
                    'today_procedure': treatments[0] if treatments else 'Consultation'
                })

        db.close()

        return jsonify({
            'success': True,
            'patients': patients,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page if total_count > 0 else 1
        }), 200

    except Exception as e:
        print(f"Get my patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Dashboard Stats for My Patients
# =========================================

@my_patients_bp.route('/stats', methods=['GET'])
@login_required
@doctor_required
def get_patient_stats():
    """Get patient statistics for the doctor"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total patients
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ? AND p.status = 'active'
            """, (doctor_id,))
            stats['total_patients'] = cursor.fetchone()['total']

            # Today's appointments (pending only - not completed)
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ? 
                AND a.appointment_date = date('now')
                AND a.status NOT IN ('completed', 'cancelled')
            """, (doctor_id,))
            stats['today_appointments'] = cursor.fetchone()['total']

            # Pending follow-ups (waiting or in_progress status)
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ? 
                AND a.status IN ('waiting', 'in_progress')
            """, (doctor_id,))
            stats['pending_followups'] = cursor.fetchone()['total']

            # Active treatments (patients with appointments in last 30 days, not completed)
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.doctor_id = ? 
                AND a.appointment_date >= date(date('now'), '-30 days')
                AND a.status NOT IN ('cancelled', 'completed')
            """, (doctor_id,))
            stats['active_treatments'] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get patient stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Get Patient Details for Modal
# =========================================

@my_patients_bp.route('/<int:patient_id>', methods=['GET'])
@login_required
@doctor_required
def get_patient_details(patient_id):
    """Get detailed patient information for modal view"""
    try:
        doctor_id = session.get('user_id')
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
                    p.address,
                    p.emergency_contact_name,
                    p.emergency_contact_phone,
                    p.insurance_provider,
                    p.policy_number,
                    p.allergies,
                    p.chronic_conditions,
                    p.current_medications,
                    p.medical_alerts,
                    p.registration_date,
                    (SELECT COUNT(*) FROM appointments WHERE patient_id = p.id AND doctor_id = ?) as total_visits,
                    (SELECT MAX(appointment_date) FROM appointments WHERE patient_id = p.id AND doctor_id = ?) as last_visit
                FROM patients p
                WHERE p.id = ?
            """, (doctor_id, doctor_id, patient_id))

            patient = cursor.fetchone()

            if not patient:
                return jsonify({'error': 'Patient not found'}), 404

            # Calculate age
            age = None
            if patient['dob']:
                today = datetime.now().date()
                age = today.year - patient['dob'].year - (
                    (today.month, today.day) < (patient['dob'].month, patient['dob'].day))

            # Get appointment history
            cursor.execute("""
                SELECT 
                    a.appointment_date,
                    a.start_time,
                    a.status,
                    a.room,
                    GROUP_CONCAT(s.name, ', ') as procedures
                FROM appointments a
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.patient_id = ? AND a.doctor_id = ?
                GROUP BY a.id
                ORDER BY a.appointment_date DESC
                LIMIT 5
            """, (patient_id, doctor_id))
            appointments = cursor.fetchall()

            # Get medical notes
            cursor.execute("""
                SELECT 
                    note_date,
                    note_type,
                    content
                FROM medical_notes
                WHERE patient_id = ? AND author_id = ?
                ORDER BY note_date DESC
                LIMIT 10
            """, (patient_id, doctor_id))
            notes = cursor.fetchall()

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
                'total_visits': patient['total_visits'],
                'last_visit': patient['last_visit'].strftime('%b %d, %Y') if patient['last_visit'] else 'Never',
                'registration_date': patient['registration_date'].strftime('%b %d, %Y') if patient['registration_date'] else '',
                'appointment_history': [
                    {
                        'date': a['appointment_date'].strftime('%b %d, %Y') if a['appointment_date'] else '',
                        'time': format_time(a['start_time']),
                        'status': a['status'],
                        'room': a['room'] or 'TBD',
                        'procedures': a['procedures'] or 'Consultation'
                    } for a in appointments
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
# Start Consultation - Update Appointment Status
# =========================================

@my_patients_bp.route('/start-consultation', methods=['POST'])
@login_required
@doctor_required
def start_consultation():
    """Start a consultation - update appointment status to in_progress"""
    try:
        doctor_id = session.get('user_id')
        data = request.get_json()
        appointment_id = data.get('appointment_id')

        if not appointment_id:
            return jsonify({'error': 'Appointment ID required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if appointment exists and belongs to this doctor
            cursor.execute("""
                SELECT id, patient_id, status FROM appointments 
                WHERE id = ? AND doctor_id = ?
            """, (appointment_id, doctor_id))
            appointment = cursor.fetchone()

            if not appointment:
                return jsonify({'error': 'Appointment not found'}), 404

            if appointment['status'] == 'completed':
                return jsonify({'error': 'Appointment is already completed'}), 400

            if appointment['status'] == 'in_progress':
                return jsonify({'error': 'Consultation already in progress'}), 400

            # Update appointment status to in_progress
            cursor.execute("""
                UPDATE appointments 
                SET status = 'in_progress', updated_at = datetime('now')
                WHERE id = ?
            """, (appointment_id,))

            # Create a medical note for the start of consultation
            cursor.execute("""
                INSERT INTO medical_notes (patient_id, author_id, appointment_id, note_date, note_type, content)
                VALUES (?, ?, ?, datetime('now'), 'pre-op', 'Consultation started. Patient is in the room.')
            """, (appointment['patient_id'], doctor_id, appointment_id))

            # Log the action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'START_CONSULTATION', 'appointments', ?, ?)
            """, (doctor_id, appointment_id, json.dumps({'status': 'in_progress'})))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Consultation started',
            'appointment_id': appointment_id,
            'patient_id': appointment['patient_id']
        }), 200

    except Exception as e:
        print(f"Start consultation error: {e}")
        return jsonify({'error': 'Failed to start consultation'}), 500
