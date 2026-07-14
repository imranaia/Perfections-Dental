# =========================================
# Perfections Dental Services
# Shared prescription logic.
#
# Workflow (v2): there is no separate pharmacy role. A doctor or nurse
# writes a prescription, it lands in a pending queue, and RECEPTION is the
# single point that dispenses the medication, deducts inventory, and bills
# the patient. A nurse may only prescribe inventory items flagged
# `nurse_eligible` (over-the-counter analgesics etc.) — anything requiring
# a doctor's sign-off (`requires_prescription`) is rejected for nurses.
# =========================================

import random
from datetime import datetime

from db import get_db


def generate_prescription_number(cursor):
    """RX-<yyyymmdd>-<sequential lastrowid-based suffix> to avoid the
    random-suffix collision risk the old doctor/prescribe.py had."""
    cursor.execute("SELECT COUNT(*) as total FROM prescriptions")
    seq = cursor.fetchone()['total'] + 1
    return f"RX-{datetime.now().strftime('%Y%m%d')}-{seq:04d}-{random.randint(10,99)}"


def create_prescription(patient_id, appointment_id, prescribed_by, role, items, notes=None):
    """items: list of dicts with inventory_item_id, dosage, frequency, duration, quantity.
    Returns (result_dict, error_message). error_message is None on success."""
    if role not in ('doctor', 'nurse'):
        return None, 'Only doctors and nurses may prescribe'
    if not items:
        return None, 'At least one medication item is required'

    db = get_db()
    try:
        with db.cursor() as cursor:
            # Validate patient & appointment exist
            cursor.execute(
                "SELECT id FROM patients WHERE id = ?", (patient_id,))
            if not cursor.fetchone():
                return None, 'Patient not found'

            if appointment_id is not None:
                cursor.execute(
                    "SELECT id FROM appointments WHERE id = ?", (appointment_id,))
                if not cursor.fetchone():
                    return None, 'Appointment not found'

            resolved_items = []
            for raw in items:
                item_id = raw.get('inventory_item_id')
                quantity = raw.get('quantity')
                if not item_id or not quantity or int(quantity) <= 0:
                    return None, 'Each item needs a valid inventory_item_id and quantity'

                cursor.execute(
                    "SELECT id, name, unit_price, requires_prescription, nurse_eligible, is_active "
                    "FROM inventory_items WHERE id = ?", (item_id,))
                item = cursor.fetchone()
                if not item or not item['is_active']:
                    return None, f'Medication {item_id} is not available'

                if role == 'nurse' and not item['nurse_eligible']:
                    return None, f"'{item['name']}' requires a doctor's prescription — a nurse cannot prescribe it"

                resolved_items.append({
                    'inventory_item_id': item['id'],
                    'unit_price': item['unit_price'],
                    'dosage': raw.get('dosage'),
                    'frequency': raw.get('frequency'),
                    'duration': raw.get('duration'),
                    'quantity': int(quantity),
                })

            prescription_number = generate_prescription_number(cursor)
            cursor.execute("""
                INSERT INTO prescriptions
                    (prescription_number, patient_id, appointment_id, prescribed_by,
                     prescribed_by_role, status, notes)
                VALUES (?, ?, ?, ?, ?, 'pending_dispense', ?)
            """, (prescription_number, patient_id, appointment_id, prescribed_by, role, notes))
            prescription_id = cursor.lastrowid

            for it in resolved_items:
                cursor.execute("""
                    INSERT INTO prescription_items
                        (prescription_id, inventory_item_id, dosage, frequency, duration, quantity, unit_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (prescription_id, it['inventory_item_id'], it['dosage'],
                      it['frequency'], it['duration'], it['quantity'], it['unit_price']))

            db.commit()
            return {
                'id': prescription_id,
                'prescription_number': prescription_number,
                'status': 'pending_dispense',
            }, None
    except Exception as e:
        db.rollback()
        return None, str(e)
    finally:
        db.close()
