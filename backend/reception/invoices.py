import sqlite3
# =========================================
# Perfections Dental Services
# Reception Invoices Module - v1.0
# =========================================

from config import Config
from db import get_db
from auth import login_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create invoices blueprint
reception_invoices_bp = Blueprint(
    'reception_invoices', __name__, url_prefix='/api/reception/invoices')



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


# =========================================
# Get All Invoices
# =========================================

@reception_invoices_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_invoices():
    """Get all invoices with filters"""
    try:
        status_filter = request.args.get('status', 'all')
        date_filter = request.args.get('date', 'all')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        invoices = []

        with db.cursor() as cursor:
            # Build query
            query = """
                SELECT 
                    i.id,
                    i.invoice_number,
                    i.invoice_date,
                    i.due_date,
                    i.status,
                    i.subtotal,
                    i.discount,
                    i.tax,
                    i.total,
                    i.notes,
                    i.created_at,
                    p.id as patient_id,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    p.patient_number,
                    p.phone,
                    COALESCE((
                        SELECT SUM(amount) FROM payments WHERE invoice_id = i.id
                    ), 0) as amount_paid
                FROM invoices i
                JOIN patients p ON i.patient_id = p.id
                WHERE 1=1
            """
            params = []

            # Apply status filter
            if status_filter != 'all':
                query += " AND i.status = ?"
                params.append(status_filter)

            # Apply date filter
            today = datetime.now().date()
            if date_filter == 'today':
                query += " AND DATE(i.invoice_date) = date('now')"
            elif date_filter == 'week':
                query += " AND i.invoice_date >= date(date('now'), '-7 days')"
            elif date_filter == 'month':
                query += " AND CAST(strftime('%m', i.invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) AND CAST(strftime('%Y', i.invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)"
            elif date_filter == 'last_month':
                query += " AND CAST(strftime('%m', i.invoice_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)"
            elif date_filter == '30':
                query += " AND i.invoice_date >= date(date('now'), '-30 days')"

            # Apply search filter
            if search:
                query += """ AND (
                    i.invoice_number LIKE ? OR 
                    p.first_name LIKE ? OR 
                    p.last_name LIKE ? OR 
                    p.patient_number LIKE ?
                )"""
                search_term = f"%{search}%"
                params.extend([search_term, search_term,
                              search_term, search_term])

            # Add ordering
            query += " ORDER BY i.invoice_date DESC, i.created_at DESC"

            # Add pagination
            offset = (page - 1) * per_page
            query += " LIMIT ? OFFSET ?"
            params.extend([per_page, offset])

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            # Get total count for pagination
            count_query = """
                SELECT COUNT(*) as total
                FROM invoices i
                JOIN patients p ON i.patient_id = p.id
                WHERE 1=1
            """
            count_params = []

            if status_filter != 'all':
                count_query += " AND i.status = ?"
                count_params.append(status_filter)

            if search:
                count_query += """ AND (
                    i.invoice_number LIKE ? OR 
                    p.first_name LIKE ? OR 
                    p.last_name LIKE ? OR 
                    p.patient_number LIKE ?
                )"""
                count_params.extend(
                    [search_term, search_term, search_term, search_term])

            cursor.execute(count_query, tuple(count_params))
            total_count = cursor.fetchone()['total']

            for row in results:
                # Get invoice items
                cursor.execute("""
                    SELECT 
                        s.name as description,
                        ast.quantity,
                        ast.unit_price as price,
                        ast.total
                    FROM appointment_services ast
                    JOIN services s ON ast.service_id = s.id
                    WHERE ast.appointment_id = (
                        SELECT appointment_id FROM invoices WHERE id = ?
                    )
                """, (row['id'],))
                items = cursor.fetchall()

                # If no items from appointment_services, get from invoices directly
                if not items and row['subtotal'] > 0:
                    # Use default items based on subtotal
                    items = [{
                        'description': 'Dental Services',
                        'quantity': 1,
                        'price': row['subtotal'],
                        'total': row['subtotal']
                    }]

                balance = row['total'] - row['amount_paid']

                invoices.append({
                    'id': row['id'],
                    'number': row['invoice_number'],
                    'patient': f"{row['patient_first']} {row['patient_last']}",
                    'patientId': row['patient_number'],
                    'patientInitials': f"{row['patient_first'][0]}{row['patient_last'][0]}",
                    'amount': float(row['total']),
                    'status': row['status'].capitalize(),
                    'date': row['invoice_date'].strftime('%Y-%m-%d'),
                    'items': items,
                    'discount': float(row['discount']),
                    'subtotal': float(row['subtotal']),
                    'tax': float(row['tax']),
                    'amount_paid': float(row['amount_paid']),
                    'balance': balance,
                    'notes': row['notes']
                })

        db.close()

        return jsonify({
            'success': True,
            'invoices': invoices,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page if total_count > 0 else 1
        }), 200

    except Exception as e:
        print(f"Get invoices error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch invoices'}), 500


# =========================================
# Get Invoice Stats
# =========================================

@reception_invoices_bp.route('/stats', methods=['GET'])
@login_required
@reception_required
def get_invoice_stats():
    """Get invoice statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total invoices
            cursor.execute(
                "SELECT COUNT(*) as total FROM invoices WHERE status != 'cancelled'")
            stats['total_invoices'] = cursor.fetchone()['total']

            # Total amount (all time)
            cursor.execute(
                "SELECT COALESCE(SUM(total), 0) as total FROM invoices WHERE status = 'paid'")
            stats['total_amount'] = float(cursor.fetchone()['total'])

            # Outstanding amount (unpaid + partial)
            cursor.execute("""
                SELECT COALESCE(SUM(total - COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id = i.id), 0)), 0) as outstanding
                FROM invoices i
                WHERE status IN ('unpaid', 'partial')
            """)
            stats['outstanding'] = float(cursor.fetchone()['outstanding'])

            # This month invoices count
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM invoices
                WHERE CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) 
                AND CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
            """)
            stats['this_month_count'] = cursor.fetchone()['total']

            # This month revenue
            cursor.execute("""
                SELECT COALESCE(SUM(total), 0) as total
                FROM invoices
                WHERE CAST(strftime('%m', invoice_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER) 
                AND CAST(strftime('%Y', invoice_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                AND status = 'paid'
            """)
            stats['this_month_revenue'] = float(cursor.fetchone()['total'])

            # Today's invoices
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM invoices
                WHERE DATE(invoice_date) = date('now')
            """)
            stats['today_count'] = cursor.fetchone()['total']

        db.close()

        return jsonify({
            'success': True,
            'stats': {
                'total_invoices': stats['total_invoices'],
                'total_amount': stats['total_amount'],
                'outstanding': stats['outstanding'],
                'this_month_count': stats['this_month_count'],
                'this_month_revenue': stats['this_month_revenue'],
                'today_count': stats['today_count']
            }
        }), 200

    except Exception as e:
        print(f"Get invoice stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Get Single Invoice by ID
# =========================================

@reception_invoices_bp.route('/<int:invoice_id>', methods=['GET'])
@login_required
@reception_required
def get_invoice(invoice_id):
    """Get single invoice details"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    i.id,
                    i.invoice_number,
                    i.invoice_date,
                    i.due_date,
                    i.status,
                    i.subtotal,
                    i.discount,
                    i.tax,
                    i.total,
                    i.notes,
                    i.created_at,
                    p.id as patient_id,
                    p.first_name as patient_first,
                    p.last_name as patient_last,
                    p.patient_number,
                    p.phone,
                    p.email,
                    p.address,
                    p.dob,
                    p.gender,
                    COALESCE((
                        SELECT SUM(amount) FROM payments WHERE invoice_id = i.id
                    ), 0) as amount_paid
                FROM invoices i
                JOIN patients p ON i.patient_id = p.id
                WHERE i.id = ?
            """, (invoice_id,))

            row = cursor.fetchone()

            if not row:
                return jsonify({'error': 'Invoice not found'}), 404

            # Get invoice items
            cursor.execute("""
                SELECT 
                    s.name as description,
                    ast.quantity,
                    ast.unit_price as price,
                    ast.total
                FROM appointment_services ast
                JOIN services s ON ast.service_id = s.id
                WHERE ast.appointment_id = (
                    SELECT appointment_id FROM invoices WHERE id = ?
                )
            """, (invoice_id,))
            items = cursor.fetchall()

            # Get payments
            cursor.execute("""
                SELECT 
                    id,
                    amount,
                    payment_method,
                    reference,
                    payment_date,
                    notes,
                    received_by
                FROM payments
                WHERE invoice_id = ?
                ORDER BY payment_date DESC
            """, (invoice_id,))
            payments = cursor.fetchall()

            invoice = {
                'id': row['id'],
                'number': row['invoice_number'],
                'date': row['invoice_date'].strftime('%Y-%m-%d'),
                'due_date': row['due_date'].strftime('%Y-%m-%d') if row['due_date'] else '',
                'status': row['status'],
                'subtotal': float(row['subtotal']),
                'discount': float(row['discount']),
                'tax': float(row['tax']),
                'total': float(row['total']),
                'amount_paid': float(row['amount_paid']),
                'balance': float(row['total']) - float(row['amount_paid']),
                'notes': row['notes'],
                'patient': {
                    'id': row['patient_id'],
                    'name': f"{row['patient_first']} {row['patient_last']}",
                    'patient_number': row['patient_number'],
                    'phone': row['phone'],
                    'email': row['email'],
                    'address': row['address'],
                    'dob': row['dob'].strftime('%Y-%m-%d') if row['dob'] else '',
                    'gender': row['gender']
                },
                'items': items,
                'payments': [{
                    'id': p['id'],
                    'amount': float(p['amount']),
                    'method': p['payment_method'],
                    'reference': p['reference'],
                    'date': p['payment_date'].strftime('%Y-%m-%d') if p['payment_date'] else '',
                    'notes': p['notes']
                } for p in payments]
            }

        db.close()
        return jsonify({'success': True, 'invoice': invoice}), 200

    except Exception as e:
        print(f"Get invoice error: {e}")
        return jsonify({'error': 'Failed to fetch invoice'}), 500


# =========================================
# Create New Invoice
# =========================================

@reception_invoices_bp.route('/', methods=['POST'])
@login_required
@reception_required
def create_invoice():
    """Create a new invoice"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        patient_id = data.get('patient_id')
        items = data.get('items', [])
        discount = float(data.get('discount', 0))
        notes = data.get('notes', '')
        payment_status = data.get('payment_status', 'unpaid')
        amount_paid = float(data.get('amount_paid', 0))
        payment_method = data.get('payment_method')

        if not patient_id or not items:
            return jsonify({'error': 'Patient and items are required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Generate invoice number
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

            # Calculate subtotal
            subtotal = sum(item['quantity'] * item['price'] for item in items)

            # Calculate tax (7.5%)
            tax_rate = 7.5
            tax = round(subtotal * tax_rate / 100, 2)
            total = subtotal - discount + tax

            # Determine final status
            if amount_paid >= total:
                final_status = 'paid'
            elif amount_paid > 0:
                final_status = 'partial'
            else:
                final_status = payment_status

            # Create invoice
            cursor.execute("""
                INSERT INTO invoices (
                    invoice_number, patient_id, invoice_date, due_date,
                    status, subtotal, discount, tax, total, notes, created_by
                ) VALUES (?, ?, date('now'), date(date('now'), '+30 days'),
                    ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_number, patient_id, final_status, subtotal, discount, tax, total, notes, user_id))

            invoice_id = cursor.lastrowid

            # Create payment if amount paid > 0
            if amount_paid > 0:
                payment_method_enum = payment_method.lower() if payment_method else 'cash'
                cursor.execute("""
                    INSERT INTO payments (
                        invoice_id, amount, payment_method, reference, payment_date, notes, received_by
                    ) VALUES (?, ?, ?, ?, date('now'), ?, ?)
                """, (invoice_id, amount_paid, payment_method_enum, f"PAY-{random.randint(1000, 9999)}", "Payment for invoice", user_id))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_INVOICE', 'invoices', ?, ?)
            """, (user_id, invoice_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Invoice created successfully',
            'invoice_id': invoice_id,
            'invoice_number': invoice_number
        }), 201

    except Exception as e:
        print(f"Create invoice error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to create invoice'}), 500


# =========================================
# Update Invoice
# =========================================

@reception_invoices_bp.route('/<int:invoice_id>', methods=['PUT'])
@login_required
@reception_required
def update_invoice(invoice_id):
    """Update an existing invoice"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        status = data.get('status')
        notes = data.get('notes')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if invoice exists
            cursor.execute(
                "SELECT id FROM invoices WHERE id = ?", (invoice_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Invoice not found'}), 404

            # Update invoice
            cursor.execute("""
                UPDATE invoices 
                SET status = ?, notes = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (status, notes, invoice_id))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_INVOICE', 'invoices', ?, ?)
            """, (user_id, invoice_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Invoice updated successfully'}), 200

    except Exception as e:
        print(f"Update invoice error: {e}")
        return jsonify({'error': 'Failed to update invoice'}), 500


# =========================================
# Delete Invoice
# =========================================

@reception_invoices_bp.route('/<int:invoice_id>', methods=['DELETE'])
@login_required
@reception_required
def delete_invoice(invoice_id):
    """Delete an invoice (or mark as cancelled)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if invoice has payments
            cursor.execute(
                "SELECT COUNT(*) as count FROM payments WHERE invoice_id = ?", (invoice_id,))
            payments = cursor.fetchone()

            if payments['count'] > 0:
                # Mark as cancelled instead of deleting
                cursor.execute("""
                    UPDATE invoices SET status = 'cancelled', updated_at = datetime('now')
                    WHERE id = ?
                """, (invoice_id,))
                message = "Invoice marked as cancelled (had payments)"
            else:
                # Delete invoice
                cursor.execute(
                    "DELETE FROM invoices WHERE id = ?", (invoice_id,))
                message = "Invoice deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_INVOICE', 'invoices', ?)
            """, (session['user_id'], invoice_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': message}), 200

    except Exception as e:
        print(f"Delete invoice error: {e}")
        return jsonify({'error': 'Failed to delete invoice'}), 500


# =========================================
# Record Payment
# =========================================

@reception_invoices_bp.route('/<int:invoice_id>/payment', methods=['POST'])
@login_required
@reception_required
def record_payment(invoice_id):
    """Record a payment for an invoice"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        amount = float(data.get('amount'))
        payment_method = data.get('payment_method')
        reference = data.get('reference', '')
        notes = data.get('notes', '')

        if not amount or amount <= 0:
            return jsonify({'error': 'Valid amount is required'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get invoice details
            cursor.execute("""
                SELECT id, total, status FROM invoices WHERE id = ?
            """, (invoice_id,))
            invoice = cursor.fetchone()

            if not invoice:
                return jsonify({'error': 'Invoice not found'}), 404

            # Get total paid so far
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total_paid
                FROM payments WHERE invoice_id = ?
            """, (invoice_id,))
            total_paid = float(cursor.fetchone()['total_paid'])

            new_total_paid = total_paid + amount
            total_due = float(invoice['total'])

            # Determine new status
            if new_total_paid >= total_due:
                new_status = 'paid'
            else:
                new_status = 'partial'

            # Create payment record
            cursor.execute("""
                INSERT INTO payments (
                    invoice_id, amount, payment_method, reference, payment_date, notes, received_by
                ) VALUES (?, ?, ?, ?, date('now'), ?, ?)
            """, (invoice_id, amount, payment_method, reference, notes, user_id))

            # Update invoice status
            cursor.execute("""
                UPDATE invoices SET status = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_status, invoice_id))

            # Log payment
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'RECORD_PAYMENT', 'payments', ?, ?)
            """, (user_id, invoice_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': f'Payment of ₦{amount:,.2f} recorded successfully',
            'new_status': new_status,
            'balance': total_due - new_total_paid
        }), 200

    except Exception as e:
        print(f"Record payment error: {e}")
        return jsonify({'error': 'Failed to record payment'}), 500


# =========================================
# Get Patients for Invoice
# =========================================

@reception_invoices_bp.route('/patients', methods=['GET'])
@login_required
@reception_required
def get_patients_for_invoice():
    """Get patients for invoice selection"""
    try:
        search = request.args.get('search', '')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        patients = []

        with db.cursor() as cursor:
            query = """
                SELECT 
                    id,
                    first_name,
                    last_name,
                    patient_number,
                    phone
                FROM patients
                WHERE status = 'active'
            """
            params = []

            if search:
                query += """ AND (
                    first_name LIKE ? OR 
                    last_name LIKE ? OR 
                    patient_number LIKE ? OR 
                    phone LIKE ?
                )"""
                search_term = f"%{search}%"
                params.extend([search_term, search_term,
                              search_term, search_term])

            query += " ORDER BY last_name, first_name LIMIT 20"

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                patients.append({
                    'id': row['id'],
                    'name': f"{row['first_name']} {row['last_name']}",
                    'initials': f"{row['first_name'][0]}{row['last_name'][0]}",
                    'patient_number': row['patient_number'],
                    'phone': row['phone']
                })

        db.close()
        return jsonify({'success': True, 'patients': patients}), 200

    except Exception as e:
        print(f"Get patients error: {e}")
        return jsonify({'error': 'Failed to fetch patients'}), 500


# =========================================
# Get Services for Invoice
# =========================================

@reception_invoices_bp.route('/services', methods=['GET'])
@login_required
@reception_required
def get_services_for_invoice():
    """Get services for invoice items"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        services = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    price,
                    description
                FROM services
                WHERE is_active = 1
                ORDER BY name
            """)

            results = cursor.fetchall()

            for row in results:
                services.append({
                    'id': row['id'],
                    'name': row['name'],
                    'price': float(row['price']),
                    'description': row['description']
                })

        db.close()
        return jsonify({'success': True, 'services': services}), 200

    except Exception as e:
        print(f"Get services error: {e}")
        return jsonify({'error': 'Failed to fetch services'}), 500
