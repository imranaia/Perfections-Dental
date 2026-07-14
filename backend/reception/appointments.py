import sqlite3
# =========================================
# Perfections Dental Services
# Reception Appointments Module - v2.0 (Fixed)
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

from reception.patients import generate_patient_number

appointments_bp = Blueprint(
    'reception_appointments', __name__, url_prefix='/api/reception/appointments')



def format_time(value):
    if value is None:
        return ""
    if isinstance(value, timedelta):
        total_seconds = value.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        period = "AM" if hours < 12 else "PM"
        hour_12 = hours % 12 or 12
        return f"{hour_12}:{minutes:02d} {period}"
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    if isinstance(value, str):
        return value
    return ""


def reception_required(f):
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        if session.get('role') not in ['reception', 'superadmin']:
            return jsonify({'error': 'Access denied. Reception role required.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_clinic_settings(cursor):
    cursor.execute("SELECT setting_key, setting_value FROM clinic_settings")
    return {r['setting_key']: r['setting_value'] for r in cursor.fetchall()}


# =========================================
# Appointment Stats
# =========================================

@appointments_bp.route('/stats', methods=['GET'])
@login_required
@reception_required
def get_appointment_stats():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}
        with db.cursor() as cursor:
            for key, condition in [
                ('total',      "status NOT IN ('cancelled')"),
                ('checked_in', "status = 'checked_in'"),
                ('waiting',    "status = 'waiting'"),
                ('emergencies', "type = 'emergency'"),
                ('completed',  "status = 'completed'"),
            ]:
                cursor.execute(f"""
                    SELECT COUNT(*) as total FROM appointments
                    WHERE DATE(appointment_date) = date('now') AND {condition}
                """)
                stats[key] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Get Appointments for a Date
# =========================================

@appointments_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_appointments():
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        filter_type = request.args.get('filter', 'all')
        search = request.args.get('search', '')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        appointments = []

        with db.cursor() as cursor:
            query = """
                SELECT
                    a.id, a.appointment_number, a.start_time, a.end_time,
                    a.status, a.room, a.type, a.emergency_priority, a.notes,
                    p.id as patient_id,
                    p.first_name as patient_first, p.last_name as patient_last,
                    p.patient_number, p.phone, p.dob, p.gender,
                    d.id as doctor_id,
                    d.first_name as doctor_first, d.last_name as doctor_last,
                    d.specialization as doctor_specialization,
                    n.id as nurse_id,
                    n.first_name as nurse_first, n.last_name as nurse_last,
                    GROUP_CONCAT(s.name, ', ') as services
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN users n ON a.nurse_id = n.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE DATE(a.appointment_date) = ?
                AND a.status NOT IN ('cancelled')
            """
            params = [date]

            filter_map = {
                'emergency': "AND a.type = 'emergency'",
                'nurse':     "AND a.type = 'nurse_only'",
                'checkedin': "AND a.status = 'checked_in'",
                'waiting':   "AND a.status = 'waiting'",
                'scheduled': "AND a.status = 'scheduled'",
                'completed': "AND a.status = 'completed'",
            }
            query += filter_map.get(filter_type, '')

            if search:
                query += """ AND (
                    p.first_name LIKE ? OR p.last_name LIKE ? OR
                    (p.first_name || ' ' || p.last_name) LIKE ? OR
                    p.patient_number LIKE ? OR p.phone LIKE ?
                )"""
                st = f"%{search}%"
                params.extend([st, st, st, st, st])

            query += " GROUP BY a.id ORDER BY a.start_time"
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            status_display_map = {
                'scheduled':  'Scheduled',  'checked_in': 'Checked In',
                'waiting':    'Waiting',     'in_progress': 'In Progress',
                'completed':  'Completed',   'cancelled': 'Cancelled',
                'no_show':    'No Show'
            }

            for row in results:
                age = None
                if row['dob']:
                    today = datetime.now().date()
                    age = today.year - row['dob'].year - (
                        (today.month, today.day) < (row['dob'].month, row['dob'].day))

                appointments.append({
                    'id': row['id'],
                    'appointment_number': row['appointment_number'],
                    'start_time': format_time(row['start_time']),
                    'end_time':   format_time(row['end_time']),
                    'status':         row['status'],
                    'status_display': status_display_map.get(row['status'], row['status']),
                    'room':        row['room'] or 'TBD',
                    'type':        row['type'],
                    'is_emergency': row['type'] == 'emergency',
                    'emergency_priority': row['emergency_priority'],
                    'notes': row['notes'],
                    'patient': {
                        'id':             row['patient_id'],
                        'name':           f"{row['patient_first']} {row['patient_last']}",
                        'first_name':     row['patient_first'],
                        'last_name':      row['patient_last'],
                        'initials':       f"{row['patient_first'][0]}{row['patient_last'][0]}",
                        'patient_number': row['patient_number'],
                        'phone':          row['phone'],
                        'age':            age,
                        'gender':         row['gender']
                    },
                    'doctor': {
                        'id':             row['doctor_id'],
                        'name':           f"Dr. {row['doctor_first']} {row['doctor_last']}" if row['doctor_first'] else None,
                        'specialization': row['doctor_specialization']
                    },
                    'nurse': {
                        'id':   row['nurse_id'],
                        'name': f"Nurse {row['nurse_first']} {row['nurse_last']}" if row['nurse_first'] else None
                    },
                    'services':      row['services'].split(', ') if row['services'] else ['Consultation'],
                    'service_count': len(row['services'].split(', ')) if row['services'] else 0
                })

        db.close()
        return jsonify({'success': True, 'appointments': appointments}), 200

    except Exception as e:
        print(f"Get appointments error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch appointments'}), 500


# =========================================
# Emergency Queue
# =========================================

@appointments_bp.route('/emergency-queue', methods=['GET'])
@login_required
@reception_required
def get_emergency_queue():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    a.id, a.start_time, a.emergency_priority,
                    p.first_name, p.last_name, p.patient_number, p.phone,
                    GROUP_CONCAT(s.name, ', ') as service_name
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE DATE(a.appointment_date) = date('now')
                AND a.type = 'emergency'
                AND a.status NOT IN ('cancelled', 'completed')
                GROUP BY a.id
                ORDER BY
                    CASE a.emergency_priority
                        WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium'   THEN 3 WHEN 'low'  THEN 4
                        ELSE 5 END,
                    a.start_time
            """)
            results = cursor.fetchall()

        db.close()
        emergencies = [{
            'id':               row['id'],
            'patient_name':     f"{row['first_name']} {row['last_name']}",
            'patient_initials': f"{row['first_name'][0]}{row['last_name'][0]}",
            'patient_number':   row['patient_number'],
            'phone':            row['phone'],
            'start_time':       format_time(row['start_time']),
            'priority':         row['emergency_priority'] or 'medium',
            'service':          row['service_name'] or 'Emergency Care'
        } for row in results]

        return jsonify({'success': True, 'emergencies': emergencies}), 200

    except Exception as e:
        print(f"Get emergency queue error: {e}")
        return jsonify({'error': 'Failed to fetch emergency queue'}), 500


# =========================================
# Doctor Availability
# =========================================

@appointments_bp.route('/doctors/availability', methods=['GET'])
@login_required
@reception_required
def get_doctor_availability():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        doctors = []
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.first_name, u.last_name, u.specialization
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name IN ('doctor', 'superadmin') AND u.status = 'active'
                ORDER BY u.last_name
            """)
            results = cursor.fetchall()

            for row in results:
                cursor.execute("""
                    SELECT
                        COUNT(*) as active_count,
                        MAX(end_time) as current_end_time
                    FROM appointments
                    WHERE doctor_id = ?
                    AND DATE(appointment_date) = date('now')
                    AND status IN ('checked_in', 'waiting', 'in_progress', 'scheduled')
                """, (row['id'],))
                info = cursor.fetchone()

                if info['active_count'] == 0:
                    available, next_free = True, "Available Now"
                elif info['current_end_time'] and info['current_end_time'] > datetime.now().time():
                    available, next_free = False, f"Free at {format_time(info['current_end_time'])}"
                else:
                    available, next_free = True, "Available Now"

                doctors.append({
                    'id':                  row['id'],
                    'name':                f"Dr. {row['first_name']} {row['last_name']}",
                    'initials':            f"{row['first_name'][0]}{row['last_name'][0]}",
                    'specialization':      row['specialization'] or 'General Dentistry',
                    'available':           available,
                    'next_free':           next_free,
                    'active_appointments': info['active_count'] or 0
                })

        db.close()
        return jsonify({'success': True, 'doctors': doctors}), 200

    except Exception as e:
        print(f"Get doctor availability error: {e}")
        return jsonify({'error': 'Failed to fetch doctors'}), 500


# =========================================
# Nurses List  (FIX #1 — was never wired up)
# =========================================

@appointments_bp.route('/nurses', methods=['GET'])
@login_required
@reception_required
def get_nurses():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.first_name, u.last_name
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'nurse' AND u.status = 'active'
                ORDER BY u.last_name
            """)
            results = cursor.fetchall()

        db.close()
        nurses = [{
            'id':       r['id'],
            'name':     f"Nurse {r['first_name']} {r['last_name']}",
            'initials': f"{r['first_name'][0]}{r['last_name'][0]}"
        } for r in results]

        return jsonify({'success': True, 'nurses': nurses}), 200

    except Exception as e:
        print(f"Get nurses error: {e}")
        return jsonify({'error': 'Failed to fetch nurses'}), 500


# =========================================
# Patients for Selection
# =========================================

@appointments_bp.route('/patients', methods=['GET'])
@login_required
@reception_required
def get_patients_for_selection():
    try:
        search = request.args.get('search', '')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            query = """
                SELECT id, first_name, last_name, patient_number, phone
                FROM patients WHERE status = 'active'
            """
            params = []
            if search:
                query += """ AND (
                    first_name LIKE ? OR last_name LIKE ? OR
                    (first_name || ' ' || last_name) LIKE ? OR
                    patient_number LIKE ? OR phone LIKE ?
                )"""
                st = f"%{search}%"
                params.extend([st, st, st, st, st])
            query += " ORDER BY last_name, first_name LIMIT 20"
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

        db.close()
        patients = [{
            'id':             r['id'],
            'name':           f"{r['first_name']} {r['last_name']}",
            'initials':       f"{r['first_name'][0]}{r['last_name'][0]}",
            'patient_number': r['patient_number'],
            'phone':          r['phone']
        } for r in results]

        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get patients error: {e}")
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Services for Selection
# =========================================

@appointments_bp.route('/services', methods=['GET'])
@login_required
@reception_required
def get_services():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.name, s.price, s.duration_minutes,
                       sc.name as category_name
                FROM services s
                LEFT JOIN service_categories sc ON s.category_id = sc.id
                WHERE s.is_active = 1
                ORDER BY sc.name, s.name
            """)
            results = cursor.fetchall()

        db.close()
        services = [{
            'id':       r['id'],
            'name':     r['name'],
            'price':    float(r['price']),
            'duration': r['duration_minutes'] or 30,
            'category': r['category_name'] or 'General'
        } for r in results]

        return jsonify({'success': True, 'services': services}), 200

    except Exception as e:
        print(f"Get services error: {e}")
        return jsonify({'error': 'Failed to fetch services'}), 500


# =========================================
# Create Appointment
# =========================================

@appointments_bp.route('/create', methods=['POST'])
@login_required
@reception_required
def create_appointment():
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:

            # ── New patient creation (single transaction) ──────────────────
            patient_id = data.get('patient_id')

            if data.get('is_new_patient'):
                # Generate the number before inserting (matches reception/patients.py)
                patient_number = generate_patient_number(db, cursor)
                cursor.execute("""
                    INSERT INTO patients (
                        patient_number, first_name, last_name, dob, gender,
                        phone, email, registration_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, date('now'), 'active')
                """, (
                    patient_number,
                    data.get('first_name'), data.get('last_name'),
                    data.get('dob'),        data.get('gender'),
                    data.get('phone'),      data.get('email')
                ))
                patient_id = cursor.lastrowid

            if not patient_id:
                db.close()
                return jsonify({'error': 'Patient ID is required'}), 400

            # ── Appointment timing ─────────────────────────────────────────
            appointment_date = data.get('date')
            start_time = data.get('start_time')

            # Calculate duration from selected services
            service_ids = data.get('service_ids', [])
            total_duration = 30  # default minutes
            if service_ids:
                placeholders = ','.join(['?'] * len(service_ids))
                cursor.execute(
                    f"SELECT COALESCE(SUM(duration_minutes), 30) as dur FROM services WHERE id IN ({placeholders})",
                    tuple(service_ids)
                )
                row = cursor.fetchone()
                if row and row['dur']:
                    total_duration = int(row['dur'])

            end_time = (
                datetime.strptime(start_time, '%H:%M') +
                timedelta(minutes=total_duration)
            ).strftime('%H:%M')

            # ── Determine appointment type ─────────────────────────────────
            nurse_only = bool(data.get('nurse_only'))
            is_emergency = bool(data.get('is_emergency'))

            appt_type = (
                'emergency' if is_emergency else
                'nurse_only' if nurse_only else
                'regular'
            )
            doctor_id = None if nurse_only else data.get('doctor_id')
            # optional assisting nurse (or required for nurse_only)
            nurse_id = data.get('nurse_id')

            # ── Insert appointment with placeholder number ─────────────────
            # appointment_date is the authoritative full timestamp (also used
            # by the patient portal's own booking flow and its FCFS unique
            # slot constraint) — combine the picked date + start_time rather
            # than storing a bare date, so both booking paths collide
            # correctly on the same doctor+slot instead of silently
            # double-booking.
            full_appointment_datetime = f"{appointment_date} {start_time}:00"
            cursor.execute("""
                INSERT INTO appointments (
                    appointment_number, patient_id, doctor_id, nurse_id,
                    appointment_date, start_time, end_time,
                    status, type, emergency_priority,
                    room, notes, created_by
                ) VALUES ('PENDING', ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?)
            """, (
                patient_id,
                doctor_id,
                nurse_id,
                full_appointment_datetime,
                start_time,
                end_time,
                appt_type,
                data.get('emergency_priority') if is_emergency else None,
                data.get('room'),
                data.get('notes', ''),
                user_id
            ))

            appointment_id = cursor.lastrowid
            appointment_number = f"APT-{datetime.now().strftime('%Y%m%d')}-{appointment_id:04d}"
            cursor.execute(
                "UPDATE appointments SET appointment_number = ? WHERE id = ?",
                (appointment_number, appointment_id)
            )

            # ── Add services ───────────────────────────────────────────────
            for service_id in service_ids:
                cursor.execute(
                    "SELECT price FROM services WHERE id = ?", (service_id,))
                svc = cursor.fetchone()
                if svc:
                    cursor.execute("""
                        INSERT INTO appointment_services
                            (appointment_id, service_id, quantity, unit_price)
                        VALUES (?, ?, 1, ?)
                    """, (appointment_id, service_id, svc['price']))

            # ── Audit log ─────────────────────────────────────────────────
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_APPOINTMENT', 'appointments', ?, ?)
            """, (user_id, appointment_id, json.dumps({
                'appointment_number': appointment_number,
                'patient_id':         patient_id,
                'type':               appt_type
            })))

            db.commit()

        db.close()
        return jsonify({
            'success':            True,
            'message':            'Appointment created successfully',
            'appointment_id':     appointment_id,
            'appointment_number': appointment_number
        }), 201

    except Exception as e:
        print(f"Create appointment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to create appointment'}), 500


# =========================================
# Update Appointment Status
# =========================================

@appointments_bp.route('/<int:appointment_id>/status', methods=['PUT'])
@login_required
@reception_required
def update_appointment_status(appointment_id):
    try:
        data = request.get_json()
        new_status = data.get('status')
        user_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE appointments SET status = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_status, appointment_id))

            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_APPOINTMENT_STATUS', 'appointments', ?, ?)
            """, (user_id, appointment_id, json.dumps({'status': new_status})))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Status updated successfully'}), 200

    except Exception as e:
        print(f"Update status error: {e}")
        return jsonify({'error': 'Failed to update status'}), 500


# =========================================
# Today's Summary
# =========================================

@appointments_bp.route('/summary', methods=['GET'])
@login_required
@reception_required
def get_today_summary():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed'  THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'checked_in' THEN 1 ELSE 0 END) as checked_in,
                    SUM(CASE WHEN status = 'waiting'    THEN 1 ELSE 0 END) as waiting,
                    SUM(CASE WHEN type = 'emergency'    THEN 1 ELSE 0 END) as emergencies,
                    SUM(CASE WHEN type = 'nurse_only'   THEN 1 ELSE 0 END) as nurse_only
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status NOT IN ('cancelled')
            """)
            row = cursor.fetchone()

        db.close()
        summary = {k: (row[k] or 0) for k in
                   ['total', 'completed', 'checked_in', 'waiting', 'emergencies', 'nurse_only']}
        return jsonify({'success': True, 'summary': summary}), 200

    except Exception as e:
        print(f"Summary error: {e}")
        return jsonify({'error': 'Failed to fetch summary'}), 500
