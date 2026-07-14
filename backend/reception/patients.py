import sqlite3
# =========================================
# Perfections Dental Services
# Reception Patients Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create patients blueprint
patients_bp = Blueprint('reception_patients', __name__,
                        url_prefix='/api/reception/patients')



def reception_required(f):
    """Decorator to require reception role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user_role = session.get('role')
        if user_role not in ['reception', 'superadmin']:
            return jsonify({'error': 'Access denied. Reception role required.'}), 403

        return f(*args, **kwargs)
    return decorated_function


def generate_patient_number(db, cursor):
    """Generate next patient number in format PAT-XXXXX"""
    try:
        # Get the last patient number
        cursor.execute(
            "SELECT patient_number FROM patients ORDER BY id DESC LIMIT 1")
        last_patient = cursor.fetchone()

        if last_patient and last_patient['patient_number']:
            # Extract number from PAT-XXXXX format
            last_num = int(last_patient['patient_number'].split('-')[1])
            next_num = last_num + 1
        else:
            next_num = 1

        # Format with leading zeros (5 digits)
        return f"PAT-{next_num:05d}"
    except Exception as e:
        print(f"Error generating patient number: {e}")
        return f"PAT-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def format_time_val(value):
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
    if hasattr(value, 'strftime'):
        return value.strftime('%I:%M %p')
    return str(value)


# =========================================
# Get All Patients
# =========================================

@patients_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_patients():
    """Get all patients with pagination and search"""
    try:
        search = request.args.get('search', '')
        status_filter = request.args.get('status', 'all')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            # Build base query
            base_query = """
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
                    p.status,
                    p.receptionist_name,
                    p.signature_date,
                    (SELECT COUNT(*) FROM appointments WHERE patient_id = p.id AND DATE(appointment_date) = date('now')) as today_appointments,
                    (SELECT COUNT(*) FROM appointments WHERE patient_id = p.id AND status IN ('scheduled', 'checked_in', 'waiting')) as active_appointments,
                    (SELECT MAX(appointment_date) FROM appointments WHERE patient_id = p.id) as last_visit,
                    (SELECT COUNT(*) FROM invoices WHERE patient_id = p.id AND status = 'unpaid') as pending_invoices,
                    (SELECT COALESCE(SUM(total), 0) FROM invoices WHERE patient_id = p.id AND status = 'unpaid') as pending_amount
                FROM patients p
                WHERE 1=1
            """

            # Build conditions
            conditions = []
            params = []

            if search:
                conditions.append("""(
                    p.first_name LIKE ? OR 
                    p.last_name LIKE ? OR 
                    p.patient_number LIKE ? OR 
                    p.phone LIKE ? OR
                    p.email LIKE ?
                )""")
                search_term = f"%{search}%"
                params.extend([search_term, search_term,
                              search_term, search_term, search_term])

            if status_filter == 'active':
                conditions.append("p.status = 'active'")
            elif status_filter == 'inactive':
                conditions.append("p.status = 'inactive'")
            elif status_filter == 'new':
                conditions.append(
                    "p.registration_date >= date(date('now'), '-30 days')")

            # Add conditions to query
            if conditions:
                base_query += " AND " + " AND ".join(conditions)

            # Count total records
            count_query = f"SELECT COUNT(*) as total FROM ({base_query}) as subquery"
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()['total']

            # Add sorting and pagination
            base_query += " ORDER BY p.registration_date DESC LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])

            cursor.execute(base_query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                # Calculate age
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - \
                        row['dob'].year - ((today.month, today.day)
                                           < (row['dob'].month, row['dob'].day))

                # Format last visit
                last_visit = row['last_visit'].strftime(
                    '%b %d, %Y') if row['last_visit'] else 'Never'

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
                    'address': row['address'],
                    'emergency_contact': {
                        'name': row['emergency_contact_name'],
                        'phone': row['emergency_contact_phone']
                    },
                    'insurance': {
                        'provider': row['insurance_provider'],
                        'policy_number': row['policy_number']
                    },
                    'medical_history': {
                        'allergies': row['allergies'],
                        'chronic_conditions': row['chronic_conditions'],
                        'current_medications': row['current_medications'],
                        'medical_alerts': row['medical_alerts']
                    },
                    'registration_date': row['registration_date'].strftime('%b %d, %Y') if row['registration_date'] else '',
                    'status': row['status'],
                    'status_display': 'Active' if row['status'] == 'active' else 'Inactive',
                    'today_appointments': row['today_appointments'],
                    'active_appointments': row['active_appointments'],
                    'last_visit': last_visit,
                    'pending_invoices': row['pending_invoices'],
                    'pending_amount': float(row['pending_amount']) if row['pending_amount'] else 0,
                    'is_new': (datetime.now().date() - row['registration_date']).days <= 30 if row['registration_date'] else False,
                    'receptionist_name': row['receptionist_name'],
                    'signature_date': row['signature_date'].strftime('%b %d, %Y') if row['signature_date'] else ''
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
        print(f"Get patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Single Patient
# =========================================

@patients_bp.route('/<int:patient_id>', methods=['GET'])
@login_required
@reception_required
def get_patient(patient_id):
    """Get single patient details"""
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
                    p.status,
                    p.receptionist_name,
                    p.signature_date,
                    p.signature_data,
                    (SELECT COUNT(*) FROM appointments WHERE patient_id = p.id) as total_visits,
                    (SELECT MAX(appointment_date) FROM appointments WHERE patient_id = p.id) as last_visit,
                    (SELECT COUNT(*) FROM invoices WHERE patient_id = p.id AND status = 'unpaid') as pending_invoices,
                    (SELECT COALESCE(SUM(total), 0) FROM invoices WHERE patient_id = p.id AND status = 'unpaid') as pending_amount
                FROM patients p
                WHERE p.id = ?
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

            # Get recent appointments
            cursor.execute("""
                SELECT 
                    a.id,
                    a.appointment_number,
                    a.appointment_date,
                    a.start_time,
                    a.status,
                    a.type,
                    d.first_name as doctor_first,
                    d.last_name as doctor_last,
                    GROUP_CONCAT(s.name, ', ') as services
                FROM appointments a
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.patient_id = ?
                GROUP BY a.id
                ORDER BY a.appointment_date DESC
                LIMIT 10
            """, (patient_id,))
            appointments = cursor.fetchall()

            # Get medical notes
            cursor.execute("""
                SELECT 
                    mn.id,
                    mn.note_date,
                    mn.note_type,
                    mn.content,
                    u.first_name as author_first,
                    u.last_name as author_last
                FROM medical_notes mn
                LEFT JOIN users u ON mn.author_id = u.id
                WHERE mn.patient_id = ?
                ORDER BY mn.note_date DESC
                LIMIT 10
            """, (patient_id,))
            notes = cursor.fetchall()

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
                'status': patient['status'],
                'total_visits': patient['total_visits'],
                'last_visit': patient['last_visit'].strftime('%b %d, %Y') if patient['last_visit'] else 'Never',
                'pending_invoices': patient['pending_invoices'],
                'pending_amount': float(patient['pending_amount']) if patient['pending_amount'] else 0,
                'receptionist_name': patient['receptionist_name'],
                'signature_date': patient['signature_date'].strftime('%b %d, %Y') if patient['signature_date'] else '',
                'signature_data': patient['signature_data'],
                'appointments': [
                    {
                        'id': a['id'],
                        'appointment_number': a['appointment_number'],
                        'date': a['appointment_date'].strftime('%b %d, %Y') if a['appointment_date'] else '',
                        'time': format_time_val(a['start_time']),
                        'status': a['status'],
                        'type': a['type'],
                        'doctor': f"Dr. {a['doctor_first']} {a['doctor_last']}" if a['doctor_first'] else 'Not assigned',
                        'services': a['services'].split(', ') if a['services'] else ['Consultation']
                    } for a in appointments
                ],
                'medical_notes': [
                    {
                        'id': n['id'],
                        'date': n['note_date'].strftime('%b %d, %Y %I:%M %p') if n['note_date'] else '',
                        'type': n['note_type'],
                        'content': n['content'],
                        'author': f"{n['author_first']} {n['author_last']}" if n['author_first'] else 'System'
                    } for n in notes
                ]
            }

        db.close()
        return jsonify({'success': True, 'patient': result}), 200

    except Exception as e:
        print(f"Get patient error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patient'}), 500


# =========================================
# Create New Patient
# =========================================

@patients_bp.route('/', methods=['POST'])
@login_required
@reception_required
def create_patient():
    """Create a new patient"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Generate patient number automatically
            patient_number = generate_patient_number(db, cursor)

            # Insert new patient
            cursor.execute("""
                INSERT INTO patients (
                    patient_number, first_name, last_name, dob, gender,
                    phone, email, address, emergency_contact_name, emergency_contact_phone,
                    insurance_provider, policy_number, allergies, chronic_conditions,
                    current_medications, medical_alerts, registration_date, status,
                    receptionist_name, signature_date, signature_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), 'active', ?, ?, ?)
            """, (
                patient_number,
                data.get('first_name'),
                data.get('last_name'),
                data.get('dob'),
                data.get('gender'),
                data.get('phone'),
                data.get('email'),
                data.get('address'),
                data.get('emergency_contact_name'),
                data.get('emergency_contact_phone'),
                data.get('insurance_provider'),
                data.get('policy_number'),
                data.get('allergies'),
                data.get('chronic_conditions'),
                data.get('current_medications'),
                data.get('medical_alerts'),
                data.get('receptionist_name'),
                data.get('signature_date'),
                data.get('signature_data')
            ))

            patient_id = cursor.lastrowid

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_PATIENT', 'patients', ?, ?)
            """, (session['user_id'], patient_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Patient created successfully',
            'patient_id': patient_id,
            'patient_number': patient_number
        }), 201

    except Exception as e:
        print(f"Create patient error: {e}")
        return jsonify({'error': 'Failed to create patient'}), 500


# =========================================
# Update Patient
# =========================================

@patients_bp.route('/<int:patient_id>', methods=['PUT'])
@login_required
@reception_required
def update_patient(patient_id):
    """Update patient details"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if patient exists
            cursor.execute(
                "SELECT id FROM patients WHERE id = ?", (patient_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Patient not found'}), 404

            # Update patient
            cursor.execute("""
                UPDATE patients SET
                    first_name = ?,
                    last_name = ?,
                    dob = ?,
                    gender = ?,
                    phone = ?,
                    email = ?,
                    address = ?,
                    emergency_contact_name = ?,
                    emergency_contact_phone = ?,
                    insurance_provider = ?,
                    policy_number = ?,
                    allergies = ?,
                    chronic_conditions = ?,
                    current_medications = ?,
                    medical_alerts = ?,
                    status = ?,
                    receptionist_name = ?,
                    signature_date = ?,
                    signature_data = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('first_name'),
                data.get('last_name'),
                data.get('dob'),
                data.get('gender'),
                data.get('phone'),
                data.get('email'),
                data.get('address'),
                data.get('emergency_contact_name'),
                data.get('emergency_contact_phone'),
                data.get('insurance_provider'),
                data.get('policy_number'),
                data.get('allergies'),
                data.get('chronic_conditions'),
                data.get('current_medications'),
                data.get('medical_alerts'),
                data.get('status', 'active'),
                data.get('receptionist_name'),
                data.get('signature_date'),
                data.get('signature_data'),
                patient_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_PATIENT', 'patients', ?, ?)
            """, (session['user_id'], patient_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Patient updated successfully'}), 200

    except Exception as e:
        print(f"Update patient error: {e}")
        return jsonify({'error': 'Failed to update patient'}), 500


# =========================================
# Delete/Deactivate Patient
# =========================================

@patients_bp.route('/<int:patient_id>', methods=['DELETE'])
@login_required
@reception_required
def delete_patient(patient_id):
    """Deactivate or delete patient"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if patient has appointments
            cursor.execute(
                "SELECT COUNT(*) as count FROM appointments WHERE patient_id = ?", (patient_id,))
            appointments = cursor.fetchone()

            if appointments['count'] > 0:
                # Mark as inactive
                cursor.execute("""
                    UPDATE patients SET status = 'inactive', updated_at = datetime('now')
                    WHERE id = ?
                """, (patient_id,))
                message = "Patient marked as inactive (has existing appointments)"
            else:
                # Delete patient
                cursor.execute(
                    "DELETE FROM patients WHERE id = ?", (patient_id,))
                message = "Patient deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_PATIENT', 'patients', ?)
            """, (session['user_id'], patient_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': message}), 200

    except Exception as e:
        print(f"Delete patient error: {e}")
        return jsonify({'error': 'Failed to delete patient'}), 500


# =========================================
# Get Patient Stats
# =========================================

@patients_bp.route('/stats', methods=['GET'])
@login_required
@reception_required
def get_patient_stats():
    """Get patient statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total patients
            cursor.execute(
                "SELECT COUNT(*) as total FROM patients WHERE status = 'active'")
            stats['total'] = cursor.fetchone()['total']

            # New patients this month
            cursor.execute("""
                SELECT COUNT(*) as total FROM patients 
                WHERE CAST(strftime('%m', registration_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) 
                AND CAST(strftime('%Y', registration_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            stats['new_this_month'] = cursor.fetchone()['total']

            # Active patients (with appointments in last 30 days)
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN appointments a ON p.id = a.patient_id
                WHERE a.appointment_date >= date(date('now'), '-30 days')
                AND p.status = 'active'
            """)
            stats['active'] = cursor.fetchone()['total']

            # Patients with pending payments
            cursor.execute("""
                SELECT COUNT(DISTINCT p.id) as total
                FROM patients p
                JOIN invoices i ON p.id = i.patient_id
                WHERE i.status = 'unpaid'
                AND p.status = 'active'
            """)
            stats['with_pending_payments'] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500
