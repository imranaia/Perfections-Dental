import sqlite3
# =========================================
# Perfections Dental Services
# Reception Payments Module - v3.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

payments_bp = Blueprint('reception_payments', __name__,
                        url_prefix='/api/reception/payments')



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

    line_items.append({
        'name': 'Consultation Fee', 'price': consultation_fee,
        'quantity': 1, 'total': consultation_fee, 'item_type': 'fee'
    })
    subtotal += consultation_fee

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

    cursor.execute("""
        SELECT ii.id as item_id, ii.name AS medication_name, ii.unit,
               ii.price AS unit_price,
               pi.id as prescription_item_id,
               pi.dosage, pi.frequency, pi.duration, pi.instructions,
               pi.quantity AS prescribed_qty,
               pr.id as prescription_id
        FROM prescriptions pr
        JOIN prescription_items pi ON pr.id = pi.prescription_id
        JOIN inventory_items ii ON pi.inventory_item_id = ii.id
        WHERE pr.patient_id = ? AND pr.status = 'active'
        AND DATE(pr.prescription_date) = date('now')
    """, (patient_id,))
    meds = cursor.fetchall()
    medications_display = []
    for med in meds:
        med_price = float(med['unit_price'] or 0)
        qty = int(med['prescribed_qty'] or 1)
        med_total = med_price * qty
        line_items.append({
            'name': med['medication_name'], 'price': med_price,
            'quantity': qty, 'total': med_total, 'item_type': 'medication',
            'item_id': med['item_id'],
            'prescription_item_id': med['prescription_item_id']
        })
        medications_display.append({
            'name': med['medication_name'], 'unit': med['unit'],
            'dosage': med['dosage'], 'frequency': med['frequency'],
            'duration': med['duration'], 'price': med_total,
            'instructions': med['instructions'],
            'item_id': med['item_id'],
            'prescription_item_id': med['prescription_item_id']
        })
        subtotal += med_total

    tax = round(subtotal * tax_percent / 100, 2)
    total = round(subtotal + tax, 2)
    return line_items, medications_display, subtotal, tax, total, is_new_today


# =========================================
# Payment Stats
# =========================================

@payments_bp.route('/stats', methods=['GET'])
@login_required
@reception_required
def get_payment_stats():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}
        with db.cursor() as cursor:
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
                SELECT COUNT(*) as c FROM payments
                WHERE DATE(payment_date) = date('now')
            """)
            stats['total_transactions'] = cursor.fetchone()['c']

            cursor.execute("""
                SELECT COUNT(*) as c FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                WHERE DATE(p.payment_date) = date('now') AND i.status = 'paid'
            """)
            stats['paid_count'] = cursor.fetchone()['c']

            cursor.execute("""
                SELECT COUNT(*) as c FROM payments
                WHERE DATE(payment_date) = date('now')
                AND payment_method = 'free'
            """)
            stats['free_count'] = cursor.fetchone()['c']

            stats['avg_ticket'] = (
                stats['today_revenue'] / stats['paid_count']
                if stats['paid_count'] > 0 else 0
            )

            cursor.execute("""
                SELECT COUNT(*) as c
                FROM appointments a
                LEFT JOIN invoices i ON i.appointment_id = a.id
                WHERE a.status NOT IN ('cancelled')
                AND i.id IS NULL
            """)
            stats['pending_approvals'] = cursor.fetchone()['c']

            cursor.execute("""
                SELECT payment_method,
                       COUNT(*) as count,
                       COALESCE(SUM(amount), 0) as total
                FROM payments WHERE DATE(payment_date) = date('now')
                GROUP BY payment_method
            """)
            stats['payment_breakdown'] = {
                r['payment_method']: {
                    'count': r['count'], 'total': float(r['total'])}
                for r in cursor.fetchall()
            }

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Payment stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Search Patients Who Have NOT Paid
# =========================================

@payments_bp.route('/patients/pending', methods=['GET'])
@login_required
@reception_required
def get_patients_unpaid():
    try:
        search = request.args.get('q', '').strip()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []
        with db.cursor() as cursor:
            query = """
                SELECT
                    p.id, p.first_name, p.last_name,
                    p.patient_number, p.phone, p.registration_date,
                    a.id AS appointment_id,
                    a.start_time, a.status AS appointment_status,
                    GROUP_CONCAT(s.name, ', ') AS services
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                LEFT JOIN invoices i ON i.appointment_id = a.id
                LEFT JOIN appointment_services ast ON ast.appointment_id = a.id
                LEFT JOIN services s ON s.id = ast.service_id
                WHERE a.status NOT IN ('cancelled')
                AND i.id IS NULL
                AND p.status = 'active'
            """
            params = []
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
                    'services':           row['services'] or 'Consultation',
                    'is_new':             is_new,
                    'pending_invoices':   1,
                    'pending_amount':     0
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get unpaid patients error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Bill Preview for Payments Page
# =========================================

@payments_bp.route('/bill/<int:appointment_id>', methods=['GET'])
@login_required
@reception_required
def get_appointment_bill(appointment_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, a.patient_id, a.status,
                       p.first_name, p.last_name,
                       p.patient_number, p.phone
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                WHERE a.id = ?
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
                return jsonify(
                    {'error': 'This appointment already has an invoice'}), 400

            settings = get_clinic_settings(cursor)
            line_items, medications, subtotal, tax, total, is_new = \
                build_bill_for_appointment(
                    cursor, appointment_id, appt['patient_id'], settings)

        db.close()

        services_display = [
            i for i in line_items if i['item_type'] in ('fee', 'service')]

        return jsonify({'success': True, 'bill': {
            'appointment_id': appointment_id,
            'patient_id':     appt['patient_id'],
            'patient_name':   f"{appt['first_name']} {appt['last_name']}",
            'patient_number': appt['patient_number'],
            'phone':          appt['phone'],
            'services':       services_display,
            'medications':    medications,
            'subtotal':       subtotal,
            'tax':            tax,
            'total':          total,
            'tax_percent':    float(settings.get('tax_rate', 7.5)),
            'is_new_patient': is_new
        }}), 200

    except Exception as e:
        print(f"Get bill error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to build bill'}), 500


# =========================================
# Process Payment — Payments Page
# Respects removed items sent from frontend
# =========================================

@payments_bp.route('/process', methods=['POST'])
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
                SELECT a.id, a.patient_id, a.status
                FROM appointments a
                WHERE a.id = ? AND a.status NOT IN ('cancelled')
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
                return jsonify(
                    {'error': 'Payment already processed for this appointment'}
                ), 400

            patient_id = appt['patient_id']
            settings = get_clinic_settings(cursor)

            # Build full bill
            line_items, medications, subtotal_full, tax_full, total_full, is_new = \
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

            # Inventory — only active medications
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

            # Audit log
            cursor.execute("""
                INSERT INTO audit_logs
                    (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'PROCESS_PAYMENT', 'invoices', ?, ?)
            """, (user_id, invoice_id, json.dumps({
                'invoice_number':      invoice_number,
                'appointment_id':      appointment_id,
                'amount':              amount,
                'method':              payment_method,
                'removed_services':    removed_service_names,
                'removed_medications': removed_medication_names,
            })))

            db.commit()

        db.close()
        return jsonify({
            'success':        True,
            'message':        'Payment processed successfully',
            'invoice_number': invoice_number,
            'receipt_number': invoice_number,
            'amount':         amount,
            'status':         'paid'
        }), 200

    except Exception as e:
        print(f"Process payment error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to process payment'}), 500


# =========================================
# Get Patient Prescriptions
# =========================================

@payments_bp.route('/prescription/<int:patient_id>', methods=['GET'])
@login_required
@reception_required
def get_patient_prescriptions(patient_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    pr.id, pr.prescription_number,
                    pr.prescription_date, pr.notes,
                    u.first_name as doc_first, u.last_name as doc_last,
                    pi.id as item_id, ii.name, ii.unit, ii.price,
                    pi.dosage, pi.frequency, pi.duration,
                    pi.instructions, pi.quantity
                FROM prescriptions pr
                JOIN prescription_items pi ON pr.id = pi.prescription_id
                JOIN inventory_items ii ON pi.inventory_item_id = ii.id
                JOIN users u ON pr.prescriber_id = u.id
                WHERE pr.patient_id = ? AND pr.status = 'active'
                AND DATE(pr.prescription_date) = date('now')
                ORDER BY pr.prescription_date DESC
            """, (patient_id,))
            rows = cursor.fetchall()

        db.close()

        pmap = {}
        for row in rows:
            pid = row['id']
            if pid not in pmap:
                pmap[pid] = {
                    'id':                  pid,
                    'prescription_number': row['prescription_number'],
                    'date':                row['prescription_date'].strftime(
                        '%b %d, %Y') if row['prescription_date'] else '',
                    'doctor':              f"Dr. {row['doc_first']} {row['doc_last']}",
                    'notes':               row['notes'],
                    'items':               []
                }
            pmap[pid]['items'].append({
                'id':           row['item_id'],
                'name':         row['name'],
                'unit':         row['unit'],
                'dosage':       row['dosage'],
                'frequency':    row['frequency'],
                'duration':     row['duration'],
                'instructions': row['instructions'],
                'price':        float(row['price'] or 0)
            })

        return jsonify(
            {'success': True, 'prescriptions': list(pmap.values())}), 200

    except Exception as e:
        print(f"Get prescriptions error: {e}")
        return jsonify({'error': 'Failed to fetch prescriptions'}), 500


# =========================================
# Recent Payments
# =========================================

@payments_bp.route('/recent', methods=['GET'])
@login_required
@reception_required
def get_recent_payments():
    try:
        limit = request.args.get('limit', 10, type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    p.id, p.amount, p.payment_method,
                    p.created_at, p.reference, i.invoice_number,
                    pt.first_name, pt.last_name, pt.patient_number
                FROM payments p
                JOIN invoices i ON p.invoice_id = i.id
                JOIN patients pt ON i.patient_id = pt.id
                WHERE DATE(p.payment_date) = date('now')
                ORDER BY p.created_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        db.close()
        payments = []
        for row in rows:
            diff = datetime.now() - \
                row['created_at'] if row['created_at'] else None
            if not diff:
                time_ago = ''
            elif diff.seconds < 60:
                time_ago = 'Just now'
            elif diff.seconds < 3600:
                time_ago = f"{diff.seconds // 60} min ago"
            elif diff.days == 0:
                h = diff.seconds // 3600
                time_ago = f"{h} hour{'s' if h > 1 else ''} ago"
            else:
                time_ago = f"{diff.days} day{'s' if diff.days > 1 else ''} ago"

            payments.append({
                'id':             row['id'],
                'patient_name':   f"{row['first_name']} {row['last_name']}",
                'patient_number': row['patient_number'],
                'invoice_number': row['invoice_number'],
                'amount':         float(row['amount']),
                'payment_method': row['payment_method'],
                'reference':      row['reference'] or '',
                'time_ago':       time_ago,
                'created_at':     row['created_at'].strftime('%I:%M %p')
                if row['created_at'] else ''
            })

        return jsonify({'success': True, 'payments': payments}), 200

    except Exception as e:
        print(f"Get recent payments error: {e}")
        return jsonify({'error': 'Failed to fetch payments'}), 500
