# =========================================
# Perfections Dental Services
# Reception Prescriptions Module — v2
#
# Reception is the single dispensing point for every prescription written
# by a doctor or nurse. There is no separate pharmacy role: reception sees
# the pending queue, dispenses the medication (deducting inventory), and
# bills the patient in the same action.
# =========================================

from functools import wraps

from flask import Blueprint, jsonify, session, request

from auth import login_required
from db import get_db

reception_prescriptions_bp = Blueprint(
    'reception_prescriptions', __name__, url_prefix='/api/reception/prescriptions')


def reception_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('reception', 'superadmin'):
            return jsonify({'error': 'Access denied. Reception role required.'}), 403
        return f(*args, **kwargs)
    return decorated


def _next_invoice_number(cursor):
    cursor.execute("SELECT COUNT(*) as total FROM invoices")
    seq = cursor.fetchone()['total'] + 1
    return f"INV-{seq:06d}"


# =========================================
# Pending dispensing queue
# =========================================
@reception_prescriptions_bp.route('/', methods=['GET'])
@login_required
@reception_required
def list_prescriptions():
    status = request.args.get('status', 'pending_dispense')
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT
                    pr.id, pr.prescription_number, pr.status, pr.notes, pr.created_at,
                    pr.prescribed_by_role,
                    p.id as patient_id, p.first_name || ' ' || p.last_name as patient_name,
                    p.phone as patient_phone,
                    u.first_name || ' ' || u.last_name as prescribed_by_name
                FROM prescriptions pr
                JOIN patients p ON pr.patient_id = p.id
                JOIN users u ON pr.prescribed_by = u.id
                WHERE (? = 'all' OR pr.status = ?)
                ORDER BY pr.created_at ASC
            """, (status, status))
            prescriptions = cursor.fetchall()

            for pres in prescriptions:
                cursor.execute("""
                    SELECT pi.id, pi.inventory_item_id, pi.dosage, pi.frequency, pi.duration,
                           pi.quantity, pi.unit_price, pi.dispensed, pi.dispensed_qty,
                           ii.name as item_name, ii.current_stock
                    FROM prescription_items pi
                    JOIN inventory_items ii ON pi.inventory_item_id = ii.id
                    WHERE pi.prescription_id = ?
                """, (pres['id'],))
                pres['items'] = cursor.fetchall()

        return jsonify({'success': True, 'prescriptions': prescriptions}), 200
    except Exception as e:
        print(f"List prescriptions error: {e}")
        return jsonify({'error': 'Failed to fetch prescriptions'}), 500
    finally:
        db.close()


# =========================================
# Dispense a prescription: deduct inventory, raise invoice, mark dispensed
# =========================================
@reception_prescriptions_bp.route('/<int:prescription_id>/dispense', methods=['POST'])
@login_required
@reception_required
def dispense_prescription(prescription_id):
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM prescriptions WHERE id = ?", (prescription_id,))
            prescription = cursor.fetchone()
            if not prescription:
                return jsonify({'error': 'Prescription not found'}), 404
            if prescription['status'] == 'dispensed':
                return jsonify({'error': 'Prescription already dispensed'}), 400

            cursor.execute("""
                SELECT pi.*, ii.name as item_name, ii.current_stock
                FROM prescription_items pi
                JOIN inventory_items ii ON pi.inventory_item_id = ii.id
                WHERE pi.prescription_id = ?
            """, (prescription_id,))
            items = cursor.fetchall()

            short_items = [i for i in items if i['current_stock']
                           < i['quantity']]
            if short_items:
                names = ', '.join(i['item_name'] for i in short_items)
                return jsonify({
                    'error': f'Insufficient stock for: {names}',
                    'short_items': [{'name': i['item_name'], 'available': i['current_stock'], 'needed': i['quantity']} for i in short_items]
                }), 409

            subtotal = 0
            for item in items:
                cursor.execute("""
                    UPDATE inventory_items
                    SET current_stock = current_stock - ?, updated_at = datetime('now')
                    WHERE id = ? AND current_stock >= ?
                """, (item['quantity'], item['inventory_item_id'], item['quantity']))
                if cursor.rowcount == 0:
                    db.rollback()
                    return jsonify({'error': f"Stock changed for '{item['item_name']}' — please retry"}), 409

                cursor.execute("""
                    INSERT INTO inventory_transactions
                        (item_id, quantity, type, reference_type, reference_id, staff_id)
                    VALUES (?, ?, 'usage', 'prescription', ?, ?)
                """, (item['inventory_item_id'], -item['quantity'], prescription_id, session['user_id']))

                cursor.execute("""
                    UPDATE prescription_items SET dispensed = 1, dispensed_qty = ?
                    WHERE id = ?
                """, (item['quantity'], item['id']))

                subtotal += item['unit_price'] * item['quantity']

            invoice_number = _next_invoice_number(cursor)
            tax = round(subtotal * 0.0, 2)  # clinic currently applies no VAT
            total = subtotal + tax
            cursor.execute("""
                INSERT INTO invoices
                    (invoice_number, patient_id, prescription_id, subtotal, tax, total, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?, 'unpaid', ?)
            """, (invoice_number, prescription['patient_id'], prescription_id,
                  subtotal, tax, total, session['user_id']))
            invoice_id = cursor.lastrowid

            for item in items:
                cursor.execute("""
                    INSERT INTO invoice_items
                        (invoice_id, description, item_type, reference_id, quantity, unit_price, line_total)
                    VALUES (?, ?, 'medication', ?, ?, ?, ?)
                """, (invoice_id, item['item_name'], item['inventory_item_id'],
                      item['quantity'], item['unit_price'], item['unit_price'] * item['quantity']))

            cursor.execute("""
                UPDATE prescriptions
                SET status = 'dispensed', dispensed_by = ?, dispensed_at = datetime('now')
                WHERE id = ?
            """, (session['user_id'], prescription_id))

            cursor.execute("""
                INSERT INTO notifications (recipient_type, recipient_id, title, body)
                VALUES ('patient', ?, 'Prescription dispensed',
                        'Your medication has been dispensed and billed. Invoice ' || ? || ' is ready for payment.')
            """, (prescription['patient_id'], invoice_number))

            db.commit()
        return jsonify({
            'success': True,
            'invoice': {'id': invoice_id, 'invoice_number': invoice_number, 'total': total}
        }), 200
    except Exception as e:
        db.rollback()
        print(f"Dispense prescription error: {e}")
        return jsonify({'error': 'Failed to dispense prescription'}), 500
    finally:
        db.close()
