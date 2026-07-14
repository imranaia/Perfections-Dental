import sqlite3
# =========================================
# Perfections Dental Services
# Nurse Prescribe Module - v1.0
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


# Create nurse prescribe blueprint
nurse_prescribe_bp = Blueprint(
    'nurse_prescribe', __name__, url_prefix='/api/nurse/prescribe')



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
# Get Today's Patients for Nurse
# =========================================

@nurse_prescribe_bp.route('/patients', methods=['GET'])
@login_required
@nurse_required
def get_today_patients():
    """Get patients the nurse is assigned to today (both assisting and nurse-only appointments)"""
    try:
        nurse_id = session.get('user_id')
        search = request.args.get('search', '')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []
        patient_ids = set()  # To avoid duplicates

        with db.cursor() as cursor:
            # 1. Get patients from assists (nurse is assisting doctor) - only active/pending appointments
            query_assists = """
                SELECT DISTINCT
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.phone,
                    p.dob,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.type,
                    GROUP_CONCAT(s.name, ', ') as procedures
                FROM assists ass
                JOIN appointments a ON ass.appointment_id = a.id
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE ass.nurse_id = ? 
                AND DATE(a.appointment_date) = date('now')
                AND a.status NOT IN ('cancelled')
                GROUP BY a.id, p.id
                ORDER BY a.start_time ASC
            """
            cursor.execute(query_assists, (nurse_id,))
            assist_results = cursor.fetchall()

            for row in assist_results:
                if row['id'] in patient_ids:
                    continue
                patient_ids.add(row['id'])

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
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'age': age,
                    'phone': row['phone'],
                    'appointment_id': row['appointment_id'],
                    'appointment_time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'type': row['type'],
                    'procedures': row['procedures'] or 'Assisting'
                })

            # 2. Get patients from nurse-only appointments (nurse is the primary provider)
            # Show ALL appointments for today, including completed, but mark them accordingly
            query_nurse_only = """
                SELECT DISTINCT
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.phone,
                    p.dob,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.type,
                    GROUP_CONCAT(s.name, ', ') as procedures
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.nurse_id = ? 
                AND DATE(a.appointment_date) = date('now')
                AND a.type = 'nurse_only'
                AND a.status NOT IN ('cancelled')
                GROUP BY a.id, p.id
                ORDER BY a.start_time ASC
            """
            cursor.execute(query_nurse_only, (nurse_id,))
            nurse_only_results = cursor.fetchall()

            for row in nurse_only_results:
                if row['id'] in patient_ids:
                    continue
                patient_ids.add(row['id'])

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
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'age': age,
                    'phone': row['phone'],
                    'appointment_id': row['appointment_id'],
                    'appointment_time': format_time(row['start_time']),
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'type': row['type'],
                    'procedures': row['procedures'] or 'Nurse Procedure'
                })

            # 3. Also get nurse-only appointments from future dates (for scheduling)
            # This will show upcoming appointments beyond today
            query_future = """
                SELECT DISTINCT
                    p.id,
                    p.patient_number,
                    p.first_name,
                    p.last_name,
                    p.phone,
                    p.dob,
                    a.id as appointment_id,
                    a.start_time,
                    a.end_time,
                    a.room,
                    a.status,
                    a.type,
                    a.appointment_date,
                    GROUP_CONCAT(s.name, ', ') as procedures
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE a.nurse_id = ? 
                AND DATE(a.appointment_date) > date('now')
                AND a.type = 'nurse_only'
                AND a.status NOT IN ('cancelled', 'completed')
                GROUP BY a.id, p.id
                ORDER BY a.appointment_date ASC, a.start_time ASC
                LIMIT 10
            """
            cursor.execute(query_future, (nurse_id,))
            future_results = cursor.fetchall()

            for row in future_results:
                if row['id'] in patient_ids:
                    continue
                patient_ids.add(row['id'])

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
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'age': age,
                    'phone': row['phone'],
                    'appointment_id': row['appointment_id'],
                    'appointment_time': format_time(row['start_time']),
                    'appointment_date': row['appointment_date'].strftime('%b %d, %Y') if row['appointment_date'] else '',
                    'room': row['room'] or 'TBD',
                    'status': row['status'],
                    'type': row['type'],
                    'procedures': row['procedures'] or 'Nurse Procedure'
                })

        # Apply search filter if provided
        if search:
            search_term = search.lower()
            patients = [p for p in patients if
                        search_term in p['full_name'].lower() or
                        search_term in p['patient_number'].lower() or
                        search_term in p['phone'].lower()]

            # Fall back to a clinic-wide active-patient search so a nurse can
            # prescribe for someone with no appointment today.
            if not patients:
                with db.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, first_name, last_name, patient_number, phone
                        FROM patients
                        WHERE status = 'active' AND (
                            first_name LIKE ? OR last_name LIKE ? OR
                            (first_name || ' ' || last_name) LIKE ? OR
                            patient_number LIKE ? OR phone LIKE ?
                        )
                        ORDER BY last_name, first_name LIMIT 20
                    """, tuple([f"%{search}%"] * 5))
                    patients = [{
                        'id': row['id'],
                        'patient_number': row['patient_number'],
                        'full_name': f"{row['first_name']} {row['last_name']}",
                        'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                        'phone': row['phone'],
                        'appointment_id': None,
                        'appointment_time': '',
                        'appointment_date': '',
                        'room': '',
                        'status': None,
                        'type': None,
                        'procedures': '',
                    } for row in cursor.fetchall()]

        # Sort by appointment date/time (today's appointments first, then future)
        patients.sort(key=lambda x: (
            x.get('appointment_date', ''), x['appointment_time']))

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get today's patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patients'}), 500

# =========================================
# Get Nurse-Eligible Medications
# =========================================


@nurse_prescribe_bp.route('/medications', methods=['GET'])
@login_required
@nurse_required
def get_nurse_medications():
    """Get medications that nurses can prescribe (OTC and some limited items)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        medications = {
            'nurse_eligible': [],
            'restricted': []
        }

        with db.cursor() as cursor:
            # Nurse-eligible medications (OTC items - requires_prescription = 0)
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    category,
                    unit,
                    current_stock as stock,
                    min_threshold,
                    price,
                    description
                FROM inventory_items
                WHERE is_active = 1 
                AND requires_prescription = 0
                ORDER BY category, name
            """)
            nurse_items = cursor.fetchall()

            for item in nurse_items:
                stock_status = 'success' if item['stock'] > item['min_threshold'] else 'warning'
                medications['nurse_eligible'].append({
                    'id': item['id'],
                    'name': item['name'],
                    'category': item['category'] or 'General',
                    'unit': item['unit'],
                    'stock': item['stock'],
                    'stock_status': stock_status,
                    'price': float(item['price']) if item['price'] else 0,
                    'description': item['description']
                })

            # Restricted medications (require doctor approval - requires_prescription = 1)
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    category,
                    unit,
                    current_stock as stock,
                    min_threshold,
                    price,
                    description
                FROM inventory_items
                WHERE is_active = 1 
                AND requires_prescription = 1
                ORDER BY category, name
            """)
            restricted_items = cursor.fetchall()

            for item in restricted_items:
                medications['restricted'].append({
                    'id': item['id'],
                    'name': item['name'],
                    'category': item['category'] or 'General',
                    'unit': item['unit'],
                    'stock': item['stock'],
                    'price': float(item['price']) if item['price'] else 0,
                    'description': item['description']
                })

        db.close()
        return jsonify({'success': True, 'medications': medications}), 200

    except Exception as e:
        print(f"Get medications error: {e}")
        return jsonify({'error': 'Failed to fetch medications'}), 500


# =========================================
# Create or Update Prescription
# =========================================

@nurse_prescribe_bp.route('/prescription', methods=['POST'])
@login_required
@nurse_required
def create_or_update_prescription():
    """Create or update a prescription for a patient"""
    try:
        data = request.get_json()
        nurse_id = session.get('user_id')

        appointment_id = data.get('appointment_id')
        patient_id = data.get('patient_id')
        items = data.get('items', [])
        notes = data.get('notes', '')

        if not appointment_id or not patient_id or not items:
            return jsonify({'error': 'Appointment, patient, and medication items required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get nurse info
            cursor.execute("""
                SELECT first_name, last_name, license_number
                FROM users WHERE id = ?
            """, (nurse_id,))
            nurse = cursor.fetchone()
            nurse_name = f"{nurse['first_name']} {nurse['last_name']}"

            import random
            prescription_number = f"RX-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

            # Check if there's already a prescription for this patient and appointment
            # Since prescriptions table doesn't have appointment_id, we'll use patient_id and date
            cursor.execute("""
                SELECT id, prescription_number FROM prescriptions 
                WHERE patient_id = ? 
                AND DATE(prescription_date) = date('now')
                AND prescriber_id = ?
                LIMIT 1
            """, (patient_id, nurse_id))
            existing_prescription = cursor.fetchone()

            prescription_id = None
            final_prescription_number = None

            if existing_prescription:
                # Update existing prescription
                prescription_id = existing_prescription['id']
                final_prescription_number = existing_prescription['prescription_number']

                # Delete existing items
                cursor.execute(
                    "DELETE FROM prescription_items WHERE prescription_id = ?", (prescription_id,))

                # Update prescription
                cursor.execute("""
                    UPDATE prescriptions 
                    SET notes = (IFNULL(notes, '') || '\n\nUpdated by nurse: ' || ? || ' at ' || datetime('now')),
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (nurse_name, prescription_id))
            else:
                # Create new prescription
                cursor.execute("""
                    INSERT INTO prescriptions (
                        prescription_number, 
                        patient_id, 
                        prescriber_id, 
                        prescription_date, 
                        status, 
                        notes
                    ) VALUES (?, ?, ?, date('now'), 'active', ?)
                """, (prescription_number, patient_id, nurse_id, notes))
                prescription_id = cursor.lastrowid
                final_prescription_number = prescription_number

            # Add prescription items
            for item in items:
                cursor.execute("""
                    INSERT INTO prescription_items (
                        prescription_id, 
                        inventory_item_id, 
                        dosage, 
                        frequency, 
                        duration, 
                        instructions, 
                        quantity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    prescription_id,
                    item['item_id'],
                    item['dosage'],
                    item['frequency'],
                    item.get('duration', '7 days'),
                    item.get('instructions', ''),
                    item.get('quantity', 1)
                ))

                # Update inventory stock
                cursor.execute("""
                    UPDATE inventory_items 
                    SET current_stock = current_stock - ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (item.get('quantity', 1), item['item_id']))

                # Log inventory transaction
                cursor.execute("""
                    INSERT INTO inventory_transactions (
                        item_id, 
                        type, 
                        quantity, 
                        transaction_date, 
                        reason, 
                        staff_id
                    ) VALUES (?, 'usage', ?, datetime('now'), 'Nurse Prescription', ?)
                """, (item['item_id'], -item.get('quantity', 1), nurse_id))

            # Log action
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, ?, 'prescriptions', ?, ?)
            """, (nurse_id, 'CREATE_PRESCRIPTION' if not existing_prescription else 'UPDATE_PRESCRIPTION', prescription_id, json.dumps({'items': items})))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Prescription saved successfully',
            'prescription_number': final_prescription_number,
            'prescription_id': prescription_id
        }), 200

    except Exception as e:
        print(f"Create/Update prescription error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to save prescription'}), 500


# =========================================
# Send prescription to Reception (v2 workflow)
# Reception is the single dispensing point. A nurse may only prescribe
# items flagged nurse_eligible — create_prescription() enforces this and
# rejects anything requiring a doctor's sign-off.
# =========================================
@nurse_prescribe_bp.route('/send-to-reception', methods=['POST'])
@login_required
@nurse_required
def send_to_reception():
    from prescriptions_shared import create_prescription

    data = request.get_json() or {}
    patient_id = data.get('patient_id')
    appointment_id = data.get('appointment_id')
    items = data.get('items', [])
    notes = data.get('notes')

    if not patient_id:
        return jsonify({'error': 'patient_id is required'}), 400

    result, error = create_prescription(
        patient_id=patient_id,
        appointment_id=appointment_id,
        prescribed_by=session['user_id'],
        role='nurse',
        items=items,
        notes=notes,
    )
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'success': True, 'prescription': result}), 201


# =========================================
# Request Doctor Approval
# =========================================

@nurse_prescribe_bp.route('/request-approval', methods=['POST'])
@login_required
@nurse_required
def request_doctor_approval():
    """Request doctor approval for restricted medications"""
    try:
        data = request.get_json()
        nurse_id = session.get('user_id')

        patient_id = data.get('patient_id')
        appointment_id = data.get('appointment_id')
        medication_name = data.get('medication_name')
        medication_id = data.get('medication_id')
        reason = data.get('reason', '')
        doctor_id = data.get('doctor_id')
        urgency = data.get('urgency', 'Routine')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get nurse info
            cursor.execute(
                "SELECT first_name, last_name FROM users WHERE id = ?", (nurse_id,))
            nurse = cursor.fetchone()
            nurse_name = f"Nurse {nurse['first_name']} {nurse['last_name']}"

            # Get doctor info
            cursor.execute(
                "SELECT first_name, last_name FROM users WHERE id = ?", (doctor_id,))
            doctor = cursor.fetchone()
            doctor_name = f"Dr. {doctor['first_name']} {doctor['last_name']}"

            # Get patient info
            cursor.execute(
                "SELECT first_name, last_name FROM patients WHERE id = ?", (patient_id,))
            patient = cursor.fetchone()
            patient_name = f"{patient['first_name']} {patient['last_name']}"

            # Create a task for doctor approval
            cursor.execute("""
                INSERT INTO tasks (
                    assigned_to, 
                    created_by, 
                    task_name, 
                    description, 
                    due_date, 
                    priority, 
                    status,
                    notes
                ) VALUES (
                    ?, ?, ?, ?, date(datetime('now'), '+1 days'), ?, 'pending', ?
                )
            """, (
                doctor_id,
                nurse_id,
                f"Prescription Approval Request: {medication_name} for {patient_name}",
                f"Patient: {patient_name}\nMedication: {medication_name}\nReason: {reason}\nAppointment ID: {appointment_id}\n\nPlease review and approve this prescription request.",
                'high' if urgency == 'Emergency' else 'medium',
                f"Requested by {nurse_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')}. Urgency: {urgency}"
            ))
            task_id = cursor.lastrowid

            # Log request
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'REQUEST_APPROVAL', 'tasks', ?, ?)
            """, (nurse_id, task_id, json.dumps({
                'medication': medication_name,
                'medication_id': medication_id,
                'reason': reason,
                'doctor': doctor_name,
                'urgency': urgency,
                'patient': patient_name,
                'appointment_id': appointment_id
            })))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': f'Approval request sent to {doctor_name}'
        }), 200

    except Exception as e:
        print(f"Request approval error: {e}")
        return jsonify({'error': 'Failed to send request'}), 500


# =========================================
# Get Available Doctors
# =========================================

@nurse_prescribe_bp.route('/doctors', methods=['GET'])
@login_required
@nurse_required
def get_available_doctors():
    """Get list of available doctors for approval requests"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        doctors = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    specialization
                FROM users
                WHERE role_id = (SELECT id FROM roles WHERE name = 'doctor')
                AND status = 'active'
                ORDER BY last_name
            """)
            results = cursor.fetchall()

            for row in results:
                doctors.append({
                    'id': row['id'],
                    'name': f"Dr. {row['first_name']} {row['last_name']}",
                    'specialization': row['specialization'] or 'General Dentistry'
                })

        db.close()
        return jsonify({'success': True, 'doctors': doctors}), 200

    except Exception as e:
        print(f"Get doctors error: {e}")
        return jsonify({'error': 'Failed to fetch doctors'}), 500


# =========================================
# Get Existing Prescription for Patient
# =========================================

@nurse_prescribe_bp.route('/appointment/<int:appointment_id>/prescription', methods=['GET'])
@login_required
@nurse_required
def get_existing_prescription(appointment_id):
    """Get existing prescription for a patient (using patient_id from appointment)"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # First get the patient_id from the appointment
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT patient_id FROM appointments WHERE id = ?", (appointment_id,))
            appointment = cursor.fetchone()
            if not appointment:
                return jsonify({'success': True, 'prescription': None}), 200

            patient_id = appointment['patient_id']

            # Get existing prescription for this patient from today
            cursor.execute("""
                SELECT 
                    p.id,
                    p.prescription_number,
                    p.prescription_date,
                    p.status,
                    p.notes,
                    pi.id as item_id,
                    pi.inventory_item_id,
                    i.name as medication_name,
                    pi.dosage,
                    pi.frequency,
                    pi.duration,
                    pi.instructions,
                    pi.quantity
                FROM prescriptions p
                LEFT JOIN prescription_items pi ON p.id = pi.prescription_id
                LEFT JOIN inventory_items i ON pi.inventory_item_id = i.id
                WHERE p.patient_id = ? 
                AND DATE(p.prescription_date) = date('now')
                AND p.prescriber_id = ?
                ORDER BY pi.id
            """, (patient_id, nurse_id))

            results = cursor.fetchall()

            if results:
                items = []
                for row in results:
                    if row['inventory_item_id']:
                        items.append({
                            'item_id': row['inventory_item_id'],
                            'name': row['medication_name'],
                            'dosage': row['dosage'],
                            'frequency': row['frequency'],
                            'duration': row['duration'],
                            'instructions': row['instructions'],
                            'quantity': row['quantity']
                        })

                prescription_data = {
                    'id': results[0]['id'],
                    'prescription_number': results[0]['prescription_number'],
                    'prescription_date': results[0]['prescription_date'].strftime('%b %d, %Y') if results[0]['prescription_date'] else '',
                    'status': results[0]['status'],
                    'notes': results[0]['notes'],
                    'items': items
                }
            else:
                prescription_data = None

        db.close()
        return jsonify({'success': True, 'prescription': prescription_data}), 200

    except Exception as e:
        print(f"Get existing prescription error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch prescription'}), 500


# =========================================
# Get Clinic Information
# =========================================

@nurse_prescribe_bp.route('/clinic-info', methods=['GET'])
@login_required
@nurse_required
def get_clinic_info():
    """Get clinic information for prescription header"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        clinic_info = {
            'name': 'Perfections Dental Services Limited',
            'email': 'info@perfections.dental',
            'phone': '+234 123 456 7890',
            'address': '23 Ikeja Way, Lagos, Nigeria'
        }

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT setting_key, setting_value
                FROM clinic_settings
                WHERE setting_key IN ('clinic_name', 'clinic_email', 'clinic_phone', 'clinic_address')
            """)
            settings = cursor.fetchall()

            for setting in settings:
                key = setting['setting_key'].replace('clinic_', '')
                clinic_info[key] = setting['setting_value']

        db.close()
        return jsonify({'success': True, 'clinic': clinic_info}), 200

    except Exception as e:
        print(f"Get clinic info error: {e}")
        return jsonify({'error': 'Failed to fetch clinic info'}), 500


# =========================================
# Get Nurse Info
# =========================================

@nurse_prescribe_bp.route('/nurse-info', methods=['GET'])
@login_required
@nurse_required
def get_nurse_info():
    """Get current nurse information"""
    try:
        nurse_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT first_name, last_name, license_number, qualifications
                FROM users WHERE id = ?
            """, (nurse_id,))
            nurse = cursor.fetchone()

        db.close()
        return jsonify({
            'success': True,
            'nurse': {
                'name': f"{nurse['first_name']} {nurse['last_name']}",
                'license': nurse['license_number'] or 'N/A',
                'qualifications': nurse['qualifications'] or 'Registered Nurse'
            }
        }), 200

    except Exception as e:
        print(f"Get nurse info error: {e}")
        return jsonify({'error': 'Failed to fetch nurse info'}), 500
