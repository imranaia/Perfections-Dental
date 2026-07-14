# =========================================
# Perfections Dental Services
# Patient Portal — Appointment requests
#
# Booking is first-come-first-served: a patient picks an open slot and the
# booking is confirmed immediately if nobody has taken it yet. A unique
# partial index on appointments(doctor_id, appointment_date) is the actual
# arbiter — if two patients race for the same slot, the database accepts
# whichever INSERT commits first and the loser gets a 409 to pick again.
# =========================================

import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, session, request

from db import get_db
from patient.auth import patient_login_required

patient_appointments_bp = Blueprint(
    'patient_appointments', __name__, url_prefix='/api/patient/appointments')

CLINIC_OPEN = 8   # 8am
CLINIC_CLOSE = 20  # 8pm, matches the public site's posted hours
SLOT_MINUTES = 30


@patient_appointments_bp.route('/doctors', methods=['GET'])
@patient_login_required
def list_doctors():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.first_name || ' ' || u.last_name as name,
                       u.specialization, u.avatar
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'doctor' AND u.status = 'active'
                ORDER BY u.first_name
            """)
            doctors = cursor.fetchall()
        return jsonify({'success': True, 'doctors': doctors}), 200
    finally:
        db.close()


@patient_appointments_bp.route('/services', methods=['GET'])
@patient_login_required
def list_services():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, price, duration_mins FROM services WHERE is_active = 1 ORDER BY name")
            services = cursor.fetchall()
        return jsonify({'success': True, 'services': services}), 200
    finally:
        db.close()


@patient_appointments_bp.route('/available-slots', methods=['GET'])
@patient_login_required
def available_slots():
    doctor_id = request.args.get('doctor_id', type=int)
    date_str = request.args.get('date')  # YYYY-MM-DD
    if not doctor_id or not date_str:
        return jsonify({'error': 'doctor_id and date are required'}), 400

    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'date must be YYYY-MM-DD'}), 400
    if day < datetime.now().date():
        return jsonify({'error': 'Cannot book a date in the past'}), 400

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT appointment_date FROM appointments
                WHERE doctor_id = ? AND DATE(appointment_date) = ? AND status != 'cancelled'
            """, (doctor_id, date_str))
            taken = {row['appointment_date'] for row in cursor.fetchall()}

        slots = []
        cur = datetime.combine(day, datetime.min.time()).replace(hour=CLINIC_OPEN)
        end = datetime.combine(day, datetime.min.time()).replace(hour=CLINIC_CLOSE)
        now = datetime.now()
        while cur < end:
            iso = cur.strftime('%Y-%m-%d %H:%M:00')
            slots.append({
                'time': cur.strftime('%H:%M'),
                'datetime': iso,
                'available': iso not in taken and cur > now,
            })
            cur += timedelta(minutes=SLOT_MINUTES)

        return jsonify({'success': True, 'date': date_str, 'slots': slots}), 200
    finally:
        db.close()


@patient_appointments_bp.route('/book', methods=['POST'])
@patient_login_required
def book_appointment():
    data = request.get_json() or {}
    doctor_id = data.get('doctor_id')
    service_id = data.get('service_id')
    slot_datetime = data.get('datetime')  # 'YYYY-MM-DD HH:MM:00'
    reason = (data.get('reason') or '').strip()

    if not doctor_id or not slot_datetime:
        return jsonify({'error': 'doctor_id and datetime are required'}), 400

    try:
        slot_dt = datetime.strptime(slot_datetime, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({'error': 'datetime must be YYYY-MM-DD HH:MM:00'}), 400
    if slot_dt <= datetime.now():
        return jsonify({'error': 'That slot is in the past'}), 400

    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO appointment_requests
                    (patient_id, preferred_doctor_id, service_id, requested_date, requested_time, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (session['patient_id'], doctor_id, service_id,
                  slot_dt.strftime('%Y-%m-%d'), slot_dt.strftime('%H:%M'), reason))
            request_id = cursor.lastrowid

            try:
                cursor.execute("""
                    INSERT INTO appointments
                        (patient_id, doctor_id, service_id, appointment_date, status, reason, created_by, request_id)
                    VALUES (?, ?, ?, ?, 'scheduled', ?, 'patient_portal', ?)
                """, (session['patient_id'], doctor_id, service_id, slot_datetime, reason, request_id))
            except sqlite3.IntegrityError:
                cursor.execute("""
                    UPDATE appointment_requests SET status = 'rejected', resolved_at = datetime('now')
                    WHERE id = ?
                """, (request_id,))
                db.commit()
                return jsonify({'error': 'That slot was just taken by another patient — please pick another.'}), 409

            appointment_id = cursor.lastrowid
            cursor.execute("""
                UPDATE appointment_requests
                SET status = 'confirmed', resolved_appointment_id = ?, resolved_at = datetime('now')
                WHERE id = ?
            """, (appointment_id, request_id))

            db.commit()
        return jsonify({
            'success': True,
            'message': 'Appointment confirmed',
            'appointment_id': appointment_id,
        }), 201
    except Exception as e:
        db.rollback()
        print(f"Book appointment error: {e}")
        return jsonify({'error': 'Failed to book appointment'}), 500
    finally:
        db.close()


@patient_appointments_bp.route('/my-requests', methods=['GET'])
@patient_login_required
def my_requests():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT ar.id, ar.requested_date, ar.requested_time, ar.status, ar.created_at,
                       u.first_name || ' ' || u.last_name as doctor_name
                FROM appointment_requests ar
                LEFT JOIN users u ON ar.preferred_doctor_id = u.id
                WHERE ar.patient_id = ?
                ORDER BY ar.created_at DESC
            """, (session['patient_id'],))
            requests_ = cursor.fetchall()
        return jsonify({'success': True, 'requests': requests_}), 200
    finally:
        db.close()
