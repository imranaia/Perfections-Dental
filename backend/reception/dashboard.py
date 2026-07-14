import sqlite3
# =========================================
# Perfections Dental Services
# Reception Dashboard Module - v3.0
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

reception_staff_bp = Blueprint(
    'reception_staff', __name__, url_prefix='/api/reception')



def format_time(value):
    if value is None:
        return ""
    if isinstance(value, timedelta):
        h = int(value.total_seconds() // 3600)
        m = int((value.total_seconds() % 3600) // 60)
        return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    if isinstance(value, time):
        return value.strftime('%I:%M %p')
    return str(value)


def reception_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        if session.get('role') not in ['reception', 'superadmin']:
            return jsonify({'error': 'Access denied'}), 403
        return f(*args, **kwargs)
    return decorated


def get_clinic_settings(cursor):
    cursor.execute("SELECT setting_key, setting_value FROM clinic_settings")
    return {r['setting_key']: r['setting_value'] for r in cursor.fetchall()}


def build_bill_for_appointment(cursor, appointment_id, patient_id, settings):
    consultation_fee = float(settings.get('consultation_fee', 10000))
    form_fee = float(settings.get('form_fee', 5000))
    tax_percent = float(settings.get('tax_rate', 7.5))
    today = datetime.now().date()

    line_items = []
    subtotal = 0.0

    # Consultation fee — always
    line_items.append({
        'name': 'Consultation Fee', 'price': consultation_fee,
        'quantity': 1, 'total': consultation_fee, 'item_type': 'fee'
    })
    subtotal += consultation_fee

    # Form fee — only if registered today
    cursor.execute(
        "SELECT registration_date FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    is_new_today = (
        patient and patient['registration_date'] is not None and
        patient['registration_date'] == today
    )
    if is_new_today:
        line_items.append({
            'name': 'New Patient Registration Fee', 'price': form_fee,
            'quantity': 1, 'total': form_fee, 'item_type': 'fee'
        })
        subtotal += form_fee

    # Services from appointment_services
    cursor.execute("""
        SELECT s.name, ast.quantity, ast.unit_price, ast.total
        FROM appointment_services ast
        JOIN services s ON ast.service_id = s.id
        WHERE ast.appointment_id = ?
    """, (appointment_id,))
    for svc in cursor.fetchall():
        svc_total = float(svc['total'])
        line_items.append({
            'name': svc['name'], 'price': float(svc['unit_price']),
            'quantity': int(svc['quantity']), 'total': svc_total,
            'item_type': 'service'
        })
        subtotal += svc_total

    # Medications from today's active prescriptions
    cursor.execute("""
        SELECT ii.id as item_id, ii.name AS medication_name, ii.unit,
               ii.price AS unit_price,
               pi.id as prescription_item_id,
               pi.dosage, pi.frequency, pi.duration, pi.instructions,
               pi.quantity AS prescribed_qty
        FROM prescriptions pr
        JOIN prescription_items pi ON pr.id = pi.prescription_id
        JOIN inventory_items ii ON pi.inventory_item_id = ii.id
        WHERE pr.patient_id = ? AND pr.status = 'active'
        AND DATE(pr.prescription_date) = date('now')
    """, (patient_id,))
    meds_display = []
    for med in cursor.fetchall():
        med_price = float(med['unit_price'] or 0)
        qty = int(med['prescribed_qty'] or 1)
        med_total = med_price * qty
        line_items.append({
            'name': med['medication_name'], 'price': med_price,
            'quantity': qty, 'total': med_total, 'item_type': 'medication',
            'item_id': med['item_id'],
            'prescription_item_id': med['prescription_item_id']
        })
        meds_display.append({
            'name': med['medication_name'], 'unit': med['unit'],
            'dosage': med['dosage'], 'frequency': med['frequency'],
            'duration': med['duration'], 'price': med_total,
            'instructions': med['instructions'],
            'item_id': med['item_id']
        })
        subtotal += med_total

    tax = round(subtotal * tax_percent / 100, 2)
    total = round(subtotal + tax, 2)
    return line_items, meds_display, subtotal, tax, total, is_new_today


# =========================================
# Dashboard Stats
# =========================================

@reception_staff_bp.route('/dashboard/stats', methods=['GET'])
@login_required
@reception_required
def get_dashboard_stats():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as total FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status NOT IN ('cancelled')
            """)
            stats['today_appointments'] = cursor.fetchone()['total']

            cursor.execute("""
                SELECT COUNT(*) as total FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status = 'checked_in'
            """)
            stats['checked_in'] = cursor.fetchone()['total']

            cursor.execute("""
                SELECT COUNT(*) as total FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status = 'scheduled'
            """)
            stats['pending'] = cursor.fetchone()['total']

            cursor.execute("""
                SELECT COUNT(*) as total FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status = 'waiting'
            """)
            stats['waiting'] = cursor.fetchone()['total']

            cursor.execute("""
                SELECT AVG(((julianday(TIME(datetime('now'))) - julianday(start_time)) * 24 * 60)) as avg_wait
                FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND status IN ('checked_in', 'waiting', 'in_progress')
                AND start_time <= TIME(datetime('now'))
            """)
            avg = cursor.fetchone()['avg_wait']
            stats['avg_wait_time'] = round(avg) if avg else 0

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total FROM payments
                WHERE DATE(payment_date) = date('now')
            """)
            stats['today_revenue'] = float(cursor.fetchone()['total'])

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total FROM payments
                WHERE DATE(payment_date) = date(date('now'), '-1 days')
            """)
            yesterday = float(cursor.fetchone()['total'])
            stats['revenue_change'] = (
                round(
                    ((stats['today_revenue'] - yesterday) / yesterday) * 100, 1)
                if yesterday > 0 else (100 if stats['today_revenue'] > 0 else 0)
            )

            cursor.execute("""
                SELECT COUNT(*) as total FROM appointments
                WHERE DATE(appointment_date) = date('now')
                AND type = 'emergency'
            """)
            stats['emergencies'] = cursor.fetchone()['total']

            cursor.execute("""
                SELECT COUNT(DISTINCT a.id) as pending_payments
                FROM appointments a
                LEFT JOIN invoices i ON a.id = i.appointment_id
                WHERE a.status NOT IN ('cancelled')
                AND i.id IS NULL
            """)
            stats['pending_payments'] = cursor.fetchone()['pending_payments']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Dashboard stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Today's Appointments
# =========================================

@reception_staff_bp.route('/appointments/today', methods=['GET'])
@login_required
@reception_required
def get_today_appointments():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        appointments = []
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    a.id, a.appointment_number, a.start_time,
                    a.status, a.room, a.type, a.emergency_priority,
                    p.id as patient_id,
                    p.first_name, p.last_name, p.patient_number, p.phone,
                    d.first_name as doc_first, d.last_name as doc_last,
                    GROUP_CONCAT(s.name, ', ') as services
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN users d ON a.doctor_id = d.id
                LEFT JOIN appointment_services ast ON a.id = ast.appointment_id
                LEFT JOIN services s ON ast.service_id = s.id
                WHERE DATE(a.appointment_date) = date('now')
                GROUP BY a.id
                ORDER BY a.start_time
            """)
            rows = cursor.fetchall()

            status_map = {
                'checked_in':  {'class': 'success',   'text': 'Checked In'},
                'waiting':     {'class': 'warning',   'text': 'Waiting'},
                'in_progress': {'class': 'info',      'text': 'In Progress'},
                'completed':   {'class': 'secondary', 'text': 'Completed'},
                'cancelled':   {'class': 'error',     'text': 'Cancelled'},
                'no_show':     {'class': 'error',     'text': 'No-show'},
            }

            for row in rows:
                appointments.append({
                    'id':               row['id'],
                    'appointment_number': row['appointment_number'],
                    'time':             format_time(row['start_time']),
                    'status':           row['status'],
                    'status_badge':     status_map.get(
                        row['status'], {'class': 'info', 'text': 'Scheduled'}),
                    'room':             row['room'] or 'TBD',
                    'type':             row['type'],
                    'is_emergency':     row['type'] == 'emergency',
                    'patient': {
                        'id':             row['patient_id'],
                        'name':           f"{row['first_name']} {row['last_name']}",
                        'initials':       f"{row['first_name'][0]}{row['last_name'][0]}",
                        'patient_number': row['patient_number'],
                        'phone':          row['phone']
                    },
                    'doctor': {
                        'name': f"Dr. {row['doc_first']} {row['doc_last']}"
                        if row['doc_first'] else 'Not assigned'
                    },
                    'services': row['services'].split(', ')
                    if row['services'] else ['Consultation']
                })

        db.close()
        return jsonify({'success': True, 'appointments': appointments}), 200

    except Exception as e:
        print(f"Get appointments error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch appointments'}), 500


# =========================================
# Search Patients Who Haven't Paid
# =========================================

@reception_staff_bp.route('/patients/search', methods=['GET'])
@login_required
@reception_required
def search_patients_for_payment():
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'success': True, 'patients': []}), 200

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []
        with db.cursor() as cursor:
            search_term = f"%{query}%"
            cursor.execute("""
                SELECT
                    p.id, p.first_name, p.last_name,
                    p.patient_number, p.phone, p.registration_date,
                    a.id AS appointment_id, a.status AS appointment_status,
                    GROUP_CONCAT(s.name, ', ') AS services
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN invoices i ON i.appointment_id = a.id
                LEFT JOIN appointment_services ast ON ast.appointment_id = a.id
                LEFT JOIN services s ON s.id = ast.service_id
                WHERE a.status NOT IN ('cancelled')
                AND i.id IS NULL
                AND p.status = 'active'
                AND (
                    p.first_name LIKE ? OR p.last_name LIKE ? OR
                    (p.first_name || ' ' || p.last_name) LIKE ? OR
                    p.patient_number LIKE ? OR p.phone LIKE ?
                )
                GROUP BY a.id
                ORDER BY a.start_time
                LIMIT 10
            """, (search_term, search_term, search_term, search_term, search_term))
            rows = cursor.fetchall()

            today = datetime.now().date()
            for row in rows:
                is_new = (
                    row['registration_date'] is not None and
                    row['registration_date'] == today
                )
                patients.append({
                    'id':                 row['id'],
                    'name':               f"{row['first_name']} {row['last_name']}",
                    'initials':           f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number':     row['patient_number'],
                    'phone':              row['phone'],
                    'appointment_id':     row['appointment_id'],
                    'appointment_status': row['appointment_status'],
                    'today_services':     row['services'] or 'Consultation',
                    'is_new':             is_new,
                    'pending_invoices':   1,
                    'pending_amount':     0
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Search patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to search patients'}), 500


# =========================================
# Get Bill Preview for Dashboard Quick Payment
# =========================================

@reception_staff_bp.route('/patient/<int:appointment_id>/invoice', methods=['GET'])
@login_required
@reception_required
def get_patient_invoice(appointment_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, a.patient_id
                FROM appointments a
                WHERE a.id = ? AND a.status NOT IN ('cancelled')
            """, (appointment_id,))
            appt = cursor.fetchone()
            if not appt:
                db.close()
                return jsonify({'error': 'Appointment not found'}), 404

            cursor.execute(
                "SELECT id, invoice_number FROM invoices WHERE appointment_id = ?",
                (appointment_id,))
            existing = cursor.fetchone()
            if existing:
                db.close()
                return jsonify({
                    'error': f'This appointment already has invoice {existing["invoice_number"]}'
                }), 400

            settings = get_clinic_settings(cursor)
            line_items, meds, subtotal, tax, total, is_new = \
                build_bill_for_appointment(
                    cursor, appointment_id, appt['patient_id'], settings)

        db.close()

        services_display = [
            i for i in line_items if i['item_type'] in ('fee', 'service')]

        return jsonify({'success': True, 'invoice': {
            'appointment_id':  appointment_id,
            'patient_id':      appt['patient_id'],
            'services':        services_display,
            'medications':     meds,
            'subtotal':        subtotal,
            'tax':             tax,
            'total':           total,
            'tax_percent':     float(settings.get('tax_rate', 7.5)),
            'is_new_patient':  is_new,
            'has_unpaid_invoice': False
        }}), 200

    except Exception as e:
        print(f"Get patient invoice error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch invoice data'}), 500


# =========================================
# Process Quick Payment — Dashboard
# Respects removed items sent from frontend
# =========================================

@reception_staff_bp.route('/payment/process', methods=['POST'])
@login_required
@reception_required
def process_payment():
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        appointment_id = data.get('appointment_id')
        payment_method = data.get('payment_method')
        reference = data.get('reference', '')
        notes = data.get('notes', '')

        # Items receptionist removed from bill before paying
        removed_service_names = data.get('removed_service_names', [])
        removed_medication_names = data.get('removed_medication_names', [])

        if not appointment_id:
            return jsonify({'error': 'appointment_id is required'}), 400
        if payment_method not in ('cash', 'pos', 'transfer', 'cheque', 'free'):
            return jsonify({'error': 'Invalid payment method'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT id, patient_id FROM appointments
                WHERE id = ? AND status NOT IN ('cancelled')
            """, (appointment_id,))
            appt = cursor.fetchone()
            if not appt:
                db.close()
                return jsonify({'error': 'Appointment not found'}), 404

            cursor.execute(
                "SELECT id FROM invoices WHERE appointment_id = ?",
                (appointment_id,))
            if cursor.fetchone():
                db.close()
                return jsonify({'error': 'Payment already processed for this appointment'}), 400

            patient_id = appt['patient_id']
            settings = get_clinic_settings(cursor)

            # Build full bill
            line_items, _, subtotal_full, tax_full, total_full, is_new = \
                build_bill_for_appointment(
                    cursor, appointment_id, patient_id, settings)

            # Filter out removed items
            active_items = [
                item for item in line_items
                if not (
                    (item['item_type'] in ('fee', 'service') and
                     item['name'] in removed_service_names) or
                    (item['item_type'] == 'medication' and
                     item['name'] in removed_medication_names)
                )
            ]

            # Recalculate totals from active items only
            tax_percent = float(settings.get('tax_rate', 7.5))
            subtotal = sum(i['total'] for i in active_items)
            tax = round(subtotal * tax_percent / 100, 2)
            total = round(subtotal + tax, 2)

            amount = 0.00 if payment_method == 'free' else total

            # Create invoice
            cursor.execute("""
                INSERT INTO invoices (
                    invoice_number, patient_id, appointment_id,
                    invoice_date, due_date, status,
                    subtotal, discount, tax, total, notes, created_by
                ) VALUES ('PENDING', ?, ?, date('now'), date('now'), 'paid',
                          ?, 0.00, ?, ?, ?, ?)
            """, (patient_id, appointment_id,
                  subtotal, tax, total, notes, user_id))

            invoice_id = cursor.lastrowid
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{invoice_id:04d}"
            cursor.execute(
                "UPDATE invoices SET invoice_number = ? WHERE id = ?",
                (invoice_number, invoice_id))

            # Payment record
            cursor.execute("""
                INSERT INTO payments (
                    invoice_id, amount, payment_method,
                    reference, payment_date, notes, received_by
                ) VALUES (?, ?, ?, ?, date('now'), ?, ?)
            """, (invoice_id, amount, payment_method, reference, notes, user_id))

            # Inventory — only for active medications
            for item in active_items:
                if item['item_type'] == 'medication':
                    cursor.execute("""
                        INSERT INTO inventory_transactions (
                            item_id, type, quantity,
                            transaction_date, reason, reference_number, staff_id
                        ) VALUES (?, 'usage', ?, datetime('now'),
                                  'Dispensed on payment', ?, ?)
                    """, (item['item_id'], -abs(item['quantity']),
                          invoice_number, user_id))
                    cursor.execute("""
                        UPDATE inventory_items
                        SET current_stock = current_stock - ?
                        WHERE id = ? AND current_stock >= ?
                    """, (item['quantity'], item['item_id'], item['quantity']))

            # Mark prescriptions dispensed only if meds were paid
            active_med_names = {
                i['name'] for i in active_items if i['item_type'] == 'medication'}
            if active_med_names:
                cursor.execute("""
                    UPDATE prescriptions SET status = 'dispensed', updated_at = datetime('now')
                    WHERE patient_id = ? AND status = 'active'
                    AND DATE(prescription_date) = date('now')
                """, (patient_id,))

            db.commit()

        db.close()
        return jsonify({
            'success':        True,
            'message':        'Payment processed successfully',
            'invoice_number': invoice_number,
            'amount':         amount
        }), 200

    except Exception as e:
        print(f"Process payment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to process payment'}), 500


# =========================================
# Doctor Availability
# =========================================

@reception_staff_bp.route('/doctors/availability', methods=['GET'])
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
                SELECT u.id, u.first_name, u.last_name, u.specialization,
                       u.status,
                       COUNT(a.id) as today_appointments,
                       SUM(CASE WHEN a.status = 'in_progress' THEN 1 ELSE 0 END)
                           as in_progress
                FROM users u
                LEFT JOIN appointments a ON u.id = a.doctor_id
                    AND DATE(a.appointment_date) = date('now')
                WHERE u.role_id IN (
                    SELECT id FROM roles WHERE name IN ('doctor', 'superadmin'))
                AND u.status = 'active'
                GROUP BY u.id ORDER BY u.last_name
            """)
            rows = cursor.fetchall()

            for row in rows:
                if row['in_progress'] and row['in_progress'] > 0:
                    availability = {'class': 'warning', 'text': 'With Patient'}
                    cursor.execute("""
                        SELECT end_time FROM appointments
                        WHERE doctor_id = ?
                        AND DATE(appointment_date) = date('now')
                        AND status = 'in_progress'
                        ORDER BY end_time DESC LIMIT 1
                    """, (row['id'],))
                    a = cursor.fetchone()
                    next_free = (f"Free: {format_time(a['end_time'])}"
                                 if a and a['end_time'] else "Free: Next hour")
                else:
                    availability = {'class': 'success', 'text': 'Available'}
                    cursor.execute("""
                        SELECT start_time FROM appointments
                        WHERE doctor_id = ?
                        AND DATE(appointment_date) = date('now')
                        AND start_time > TIME(datetime('now'))
                        AND status NOT IN ('cancelled', 'completed')
                        ORDER BY start_time ASC LIMIT 1
                    """, (row['id'],))
                    n = cursor.fetchone()
                    next_free = (f"Next: {format_time(n['start_time'])}"
                                 if n and n['start_time'] else "No more today")

                doctors.append({
                    'id':                 row['id'],
                    'name':               f"Dr. {row['first_name']} {row['last_name']}",
                    'initials':           f"{row['first_name'][0]}{row['last_name'][0]}",
                    'specialization':     row['specialization'] or 'General Dentistry',
                    'availability':       availability,
                    'next_free':          next_free,
                    'today_appointments': int(row['today_appointments'] or 0)
                })

        db.close()
        return jsonify({'success': True, 'doctors': doctors}), 200

    except Exception as e:
        print(f"Get doctors availability error: {e}")
        return jsonify({'error': 'Failed to fetch doctors availability'}), 500
