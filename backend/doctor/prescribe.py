import sqlite3
# =========================================
# Perfections Dental Services
# Doctor Prescribe Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import sys
import os
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create prescribe blueprint
prescribe_bp = Blueprint('doctor_prescribe', __name__,
                         url_prefix='/api/doctor/prescribe')



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
# Get Inventory Items (ALL active items)
# =========================================

@prescribe_bp.route('/inventory', methods=['GET'])
@login_required
@doctor_required
def get_inventory():
    """Get all inventory items for prescribing (including OTC items)"""
    try:
        search = request.args.get('search', '')
        category = request.args.get('category', 'all')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        items = []

        with db.cursor() as cursor:
            # Show ALL active inventory items, not just prescription-only
            query = """
                SELECT 
                    id,
                    name,
                    category,
                    manufacturer,
                    unit,
                    price,
                    current_stock,
                    min_threshold,
                    expiry_date,
                    requires_prescription,
                    is_active,
                    description
                FROM inventory_items
                WHERE is_active = 1
            """
            params = []

            if search:
                query += " AND (name LIKE ? OR category LIKE ? OR description LIKE ?)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])

            if category != 'all' and category != 'lowstock':
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY name"

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                # Calculate stock percentage
                stock_percentage = (
                    row['current_stock'] / row['min_threshold'] * 100) if row['min_threshold'] > 0 else 100
                stock_percentage = min(max(stock_percentage, 0), 100)

                # Determine stock status
                if row['current_stock'] <= 0:
                    stock_status = 'out-of-stock'
                    status_badge = {'text': 'Out of Stock', 'class': 'error'}
                elif row['current_stock'] <= row['min_threshold']:
                    stock_status = 'low-stock'
                    status_badge = {'text': 'Low Stock', 'class': 'warning'}
                else:
                    stock_status = 'in-stock'
                    status_badge = {'text': 'In Stock', 'class': 'success'}

                # Check expiry
                expiry_warning = False
                expiry_date_str = None
                if row['expiry_date']:
                    expiry_date_str = row['expiry_date'].strftime('%b %Y')
                    days_to_expiry = (
                        row['expiry_date'] - datetime.now().date()).days
                    if days_to_expiry <= 30 and days_to_expiry > 0:
                        expiry_warning = True
                        status_badge = {
                            'text': f'Expires in {days_to_expiry}d', 'class': 'warning'}
                    elif days_to_expiry <= 0:
                        status_badge = {'text': 'Expired', 'class': 'error'}
                        stock_status = 'out-of-stock'

                # Add prescription requirement badge
                if row['requires_prescription']:
                    rx_badge = {'text': 'Rx Required', 'class': 'info'}
                else:
                    rx_badge = {'text': 'OTC', 'class': 'secondary'}

                items.append({
                    'id': row['id'],
                    'name': row['name'],
                    'category': row['category'] or 'General',
                    'manufacturer': row['manufacturer'],
                    'unit': row['unit'],
                    'price': float(row['price']) if row['price'] else 0,
                    'current_stock': row['current_stock'],
                    'min_threshold': row['min_threshold'],
                    'stock_percentage': stock_percentage,
                    'stock_status': stock_status,
                    'status_badge': status_badge,
                    'rx_badge': rx_badge,
                    'expiry_date': expiry_date_str,
                    'expiry_warning': expiry_warning,
                    'description': row['description']
                })

            # Filter low stock if requested
            if category == 'lowstock':
                items = [i for i in items if i['stock_status']
                         in ['low-stock', 'out-of-stock']]

        db.close()

        # Get unique categories
        categories = sorted(
            list(set([i['category'] for i in items if i['category']])))

        return jsonify({
            'success': True,
            'items': items,
            'categories': categories,
            'total': len(items)
        }), 200

    except Exception as e:
        print(f"Get inventory error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch inventory'}), 500


# =========================================
# Get Patients for Doctor
# =========================================

@prescribe_bp.route('/patients', methods=['GET'])
@login_required
@doctor_required
def get_patients():
    """Get patients for the doctor. With ?search=, falls back to a clinic-wide
    active-patient search (not just today's appointments) so a doctor can
    prescribe for any patient, not only ones seen today."""
    try:
        doctor_id = session.get('user_id')
        search = request.args.get('search', '').strip()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            if search:
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
                for row in cursor.fetchall():
                    patients.append({
                        'id': row['id'],
                        'name': f"{row['first_name']} {row['last_name']}",
                        'patient_number': row['patient_number'],
                        'phone': row['phone'],
                        'status': None,
                        'status_display': ''
                    })
            else:
                # Get today's patients with appointments
                cursor.execute("""
                    SELECT DISTINCT
                        p.id,
                        p.first_name,
                        p.last_name,
                        p.patient_number,
                        p.phone,
                        a.status as today_status,
                        a.start_time
                    FROM patients p
                    JOIN appointments a ON p.id = a.patient_id
                    WHERE a.doctor_id = ?
                    AND DATE(a.appointment_date) = date('now')
                    AND p.status = 'active'
                    ORDER BY a.start_time
                """, (doctor_id,))

                results = cursor.fetchall()

                for row in results:
                    patients.append({
                        'id': row['id'],
                        'name': f"{row['first_name']} {row['last_name']}",
                        'patient_number': row['patient_number'],
                        'phone': row['phone'],
                        'status': row['today_status'],
                        'status_display': row['today_status'].replace('_', ' ').title()
                    })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get patients error: {e}")
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Low Stock Alerts
# =========================================

@prescribe_bp.route('/alerts', methods=['GET'])
@login_required
@doctor_required
def get_alerts():
    """Get inventory alerts (low stock and expiring soon)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        alerts = {
            'low_stock': [],
            'expiring': []
        }

        with db.cursor() as cursor:
            # Low stock items
            cursor.execute("""
                SELECT 
                    name,
                    current_stock,
                    min_threshold
                FROM inventory_items
                WHERE current_stock <= min_threshold 
                AND is_active = 1
                ORDER BY current_stock ASC
                LIMIT 5
            """)
            low_stock = cursor.fetchall()

            for item in low_stock:
                alerts['low_stock'].append({
                    'name': item['name'],
                    'current_stock': item['current_stock'],
                    'min_threshold': item['min_threshold']
                })

            # Expiring soon items
            cursor.execute("""
                SELECT 
                    name,
                    expiry_date
                FROM inventory_items
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+30 days')
                AND is_active = 1
                ORDER BY expiry_date ASC
                LIMIT 5
            """)
            expiring = cursor.fetchall()

            for item in expiring:
                days_to_expiry = (item['expiry_date'] -
                                  datetime.now().date()).days
                alerts['expiring'].append({
                    'name': item['name'],
                    'expiry_date': item['expiry_date'].strftime('%b %d, %Y'),
                    'days_left': days_to_expiry
                })

        db.close()
        return jsonify({'success': True, 'alerts': alerts}), 200

    except Exception as e:
        print(f"Get alerts error: {e}")
        return jsonify({'error': 'Failed to fetch alerts'}), 500


# =========================================
# Create Prescription
# =========================================

@prescribe_bp.route('/create', methods=['POST'])
@login_required
@doctor_required
def create_prescription():
    """Create a new prescription"""
    try:
        data = request.get_json()
        patient_id = data.get('patient_id')
        items = data.get('items', [])
        notes = data.get('notes', '')

        doctor_id = session.get('user_id')

        if not patient_id or not items:
            return jsonify({'error': 'Patient and medication items required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Generate prescription number
            import random
            prescription_number = f"RX-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

            # Create prescription
            cursor.execute("""
                INSERT INTO prescriptions (
                    prescription_number, 
                    patient_id, 
                    prescriber_id, 
                    prescription_date, 
                    status, 
                    notes
                ) VALUES (?, ?, ?, date('now'), 'active', ?)
            """, (prescription_number, patient_id, doctor_id, notes))

            prescription_id = cursor.lastrowid

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
                    item['duration'],
                    item.get('instructions', ''),
                    item.get('quantity', 1)
                ))

                # Update inventory stock (reduce quantity)
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
                    ) VALUES (?, 'usage', ?, datetime('now'), 'Prescription', ?)
                """, (item['item_id'], -item.get('quantity', 1), doctor_id))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_PRESCRIPTION', 'prescriptions', ?, ?)
            """, (doctor_id, prescription_id, json.dumps({'items': items})))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Prescription created successfully',
            'prescription_number': prescription_number,
            'prescription_id': prescription_id
        }), 201

    except Exception as e:
        print(f"Create prescription error: {e}")
        return jsonify({'error': 'Failed to create prescription'}), 500


# =========================================
# Send prescription to Reception (v2 workflow)
# Reception is the single dispensing point — no separate pharmacy role.
# =========================================
@prescribe_bp.route('/send-to-reception', methods=['POST'])
@login_required
@doctor_required
def send_to_reception():
    """Doctor writes a prescription; it lands in reception's dispensing queue."""
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
        role='doctor',
        items=items,
        notes=notes,
    )
    if error:
        return jsonify({'error': error}), 400
    return jsonify({'success': True, 'prescription': result}), 201


# =========================================
# Get Doctor Information
# =========================================

@prescribe_bp.route('/doctor-info', methods=['GET'])
@login_required
@doctor_required
def get_doctor_info():
    """Get current doctor information for prescription"""
    try:
        doctor_id = session.get('user_id')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    first_name,
                    last_name,
                    specialization,
                    license_number
                FROM users
                WHERE id = ?
            """, (doctor_id,))

            doctor = cursor.fetchone()

        db.close()

        return jsonify({
            'success': True,
            'doctor': {
                'name': f"Dr. {doctor['first_name']} {doctor['last_name']}",
                'specialization': doctor['specialization'] or 'Dental Surgeon',
                'license': doctor['license_number'] or ''
            }
        }), 200

    except Exception as e:
        print(f"Get doctor info error: {e}")
        return jsonify({'error': 'Failed to fetch doctor info'}), 500


# =========================================
# Get Clinic Settings
# =========================================

@prescribe_bp.route('/settings', methods=['GET'])
@login_required
@doctor_required
def get_clinic_settings():
    """Get clinic settings for prescription header"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Default clinic info
        clinic_info = {
            'name': '',
            'email': '',
            'phone': '',
            'address': ''
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
        print(f"Get clinic settings error: {e}")
        return jsonify({'error': 'Failed to fetch clinic settings'}), 500
