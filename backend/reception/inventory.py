import sqlite3
# =========================================
# Perfections Dental Services
# Reception Inventory Module - v1.0
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


# Create inventory blueprint
reception_inventory_bp = Blueprint(
    'reception_inventory', __name__, url_prefix='/api/reception/inventory')



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
# Get Inventory Items
# =========================================

@reception_inventory_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_inventory():
    """Get all inventory items with filtering"""
    try:
        search = request.args.get('search', '')
        category = request.args.get('category', 'all')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        items = []

        with db.cursor() as cursor:
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
                    max_stock,
                    location,
                    expiry_date,
                    batch_number,
                    requires_prescription,
                    is_active,
                    description,
                    notes,
                    created_at,
                    updated_at
                FROM inventory_items
                WHERE is_active = 1
            """
            params = []

            if search:
                query += " AND (name LIKE ? OR category LIKE ? OR manufacturer LIKE ?)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])

            if category != 'all':
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY name"

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                # Calculate stock status
                stock_percentage = (row['current_stock'] / row['max_stock']
                                    * 100) if row['max_stock'] and row['max_stock'] > 0 else 100
                stock_percentage = min(max(stock_percentage, 0), 100)

                if row['current_stock'] <= 0:
                    stock_status = 'critical'
                    stock_status_text = 'Out of Stock'
                elif row['current_stock'] <= row['min_threshold']:
                    stock_status = 'critical'
                    stock_status_text = 'Critical Low'
                elif row['current_stock'] <= row['min_threshold'] * 1.5:
                    stock_status = 'warning'
                    stock_status_text = 'Low Stock'
                else:
                    stock_status = 'good'
                    stock_status_text = 'In Stock'

                # Calculate expiry status
                expiry_status = 'safe'
                expiry_days = None
                if row['expiry_date']:
                    days_to_expiry = (
                        row['expiry_date'] - datetime.now().date()).days
                    expiry_days = days_to_expiry
                    if days_to_expiry <= 0:
                        expiry_status = 'critical'
                    elif days_to_expiry <= 30:
                        expiry_status = 'critical'
                    elif days_to_expiry <= 90:
                        expiry_status = 'warning'
                    else:
                        expiry_status = 'safe'

                items.append({
                    'id': row['id'],
                    'name': row['name'],
                    'category': row['category'] or 'General',
                    'manufacturer': row['manufacturer'] or '',
                    'unit': row['unit'],
                    'price': float(row['price']) if row['price'] else 0,
                    'stock': row['current_stock'],
                    'min_stock': row['min_threshold'],
                    'max_stock': row['max_stock'] or 100,
                    'stock_percentage': stock_percentage,
                    'stock_status': stock_status,
                    'stock_status_text': stock_status_text,
                    'location': row['location'] or '',
                    'expiry_date': row['expiry_date'].strftime('%Y-%m-%d') if row['expiry_date'] else None,
                    'expiry_days': expiry_days,
                    'expiry_status': expiry_status,
                    'batch': row['batch_number'] or '',
                    'prescription': row['requires_prescription'],
                    'active': row['is_active'],
                    'description': row['description'] or '',
                    'notes': row['notes'] or ''
                })

        # Get categories for filter pills
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT category 
                FROM inventory_items 
                WHERE is_active = 1 AND category IS NOT NULL
                ORDER BY category
            """)
            categories = [row['category'] for row in cursor.fetchall()]

        db.close()
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
# Get Inventory Alerts
# =========================================

@reception_inventory_bp.route('/alerts', methods=['GET'])
@login_required
@reception_required
def get_inventory_alerts():
    """Get low stock and expiring items alerts"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        alerts = {
            'critical_stock': [],
            'expiring': []
        }

        with db.cursor() as cursor:
            # Low stock items
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    current_stock,
                    min_threshold,
                    max_stock
                FROM inventory_items
                WHERE current_stock <= min_threshold
                AND is_active = 1
                ORDER BY (current_stock / min_threshold) ASC
                LIMIT 5
            """)
            low_stock = cursor.fetchall()

            for item in low_stock:
                deficit = item['min_threshold'] - item['current_stock']
                alerts['critical_stock'].append({
                    'id': item['id'],
                    'name': item['name'],
                    'current_stock': item['current_stock'],
                    'min_threshold': item['min_threshold'],
                    'deficit': deficit if deficit > 0 else 0
                })

            # Expiring soon items
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    current_stock,
                    expiry_date
                FROM inventory_items
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+90 days')
                AND is_active = 1
                AND current_stock > 0
                ORDER BY expiry_date ASC
                LIMIT 5
            """)
            expiring = cursor.fetchall()

            for item in expiring:
                days_to_expiry = (item['expiry_date'] -
                                  datetime.now().date()).days
                alerts['expiring'].append({
                    'id': item['id'],
                    'name': item['name'],
                    'current_stock': item['current_stock'],
                    'expiry_date': item['expiry_date'].strftime('%Y-%m-%d'),
                    'days_left': days_to_expiry
                })

        db.close()
        return jsonify({'success': True, 'alerts': alerts}), 200

    except Exception as e:
        print(f"Get alerts error: {e}")
        return jsonify({'error': 'Failed to fetch alerts'}), 500


# =========================================
# Get Single Inventory Item
# =========================================

@reception_inventory_bp.route('/<int:item_id>', methods=['GET'])
@login_required
@reception_required
def get_inventory_item(item_id):
    """Get single inventory item details"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id,
                    name,
                    category,
                    manufacturer,
                    unit,
                    price,
                    current_stock,
                    min_threshold,
                    max_stock,
                    location,
                    expiry_date,
                    batch_number,
                    requires_prescription,
                    is_active,
                    description,
                    notes
                FROM inventory_items
                WHERE id = ?
            """, (item_id,))

            item = cursor.fetchone()

            if not item:
                return jsonify({'error': 'Item not found'}), 404

            result = {
                'id': item['id'],
                'name': item['name'],
                'category': item['category'] or 'General',
                'manufacturer': item['manufacturer'] or '',
                'unit': item['unit'],
                'price': float(item['price']) if item['price'] else 0,
                'stock': item['current_stock'],
                'min_stock': item['min_threshold'],
                'max_stock': item['max_stock'] or 100,
                'location': item['location'] or '',
                'expiry_date': item['expiry_date'].strftime('%Y-%m-%d') if item['expiry_date'] else '',
                'batch': item['batch_number'] or '',
                'prescription': item['requires_prescription'],
                'active': item['is_active'],
                'description': item['description'] or '',
                'notes': item['notes'] or ''
            }

        db.close()
        return jsonify({'success': True, 'item': result}), 200

    except Exception as e:
        print(f"Get inventory item error: {e}")
        return jsonify({'error': 'Failed to fetch item'}), 500


# =========================================
# Create Inventory Item
# =========================================

@reception_inventory_bp.route('/', methods=['POST'])
@login_required
@reception_required
def create_inventory_item():
    """Create a new inventory item"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO inventory_items (
                    name, category, manufacturer, unit, price,
                    current_stock, min_threshold, max_stock, location,
                    expiry_date, batch_number, requires_prescription,
                    is_active, description, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('name'),
                data.get('category'),
                data.get('manufacturer'),
                data.get('unit'),
                data.get('price', 0),
                data.get('stock', 0),
                data.get('min_stock', 10),
                data.get('max_stock', 100),
                data.get('location'),
                data.get('expiry_date'),
                data.get('batch'),
                data.get('prescription', True),
                data.get('active', True),
                data.get('description'),
                data.get('notes')
            ))

            item_id = cursor.lastrowid

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_INVENTORY_ITEM', 'inventory_items', ?, ?)
            """, (user_id, item_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Item created successfully',
            'item_id': item_id
        }), 201

    except Exception as e:
        print(f"Create inventory item error: {e}")
        return jsonify({'error': 'Failed to create item'}), 500


# =========================================
# Update Inventory Item
# =========================================

@reception_inventory_bp.route('/<int:item_id>', methods=['PUT'])
@login_required
@reception_required
def update_inventory_item(item_id):
    """Update an inventory item"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if item exists
            cursor.execute(
                "SELECT id FROM inventory_items WHERE id = ?", (item_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Item not found'}), 404

            cursor.execute("""
                UPDATE inventory_items SET
                    name = ?,
                    category = ?,
                    manufacturer = ?,
                    unit = ?,
                    price = ?,
                    current_stock = ?,
                    min_threshold = ?,
                    max_stock = ?,
                    location = ?,
                    expiry_date = ?,
                    batch_number = ?,
                    requires_prescription = ?,
                    is_active = ?,
                    description = ?,
                    notes = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('name'),
                data.get('category'),
                data.get('manufacturer'),
                data.get('unit'),
                data.get('price', 0),
                data.get('stock', 0),
                data.get('min_stock', 10),
                data.get('max_stock', 100),
                data.get('location'),
                data.get('expiry_date'),
                data.get('batch'),
                data.get('prescription', True),
                data.get('active', True),
                data.get('description'),
                data.get('notes'),
                item_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_INVENTORY_ITEM', 'inventory_items', ?, ?)
            """, (user_id, item_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Item updated successfully'
        }), 200

    except Exception as e:
        print(f"Update inventory item error: {e}")
        return jsonify({'error': 'Failed to update item'}), 500


# =========================================
# Delete Inventory Item
# =========================================

@reception_inventory_bp.route('/<int:item_id>', methods=['DELETE'])
@login_required
@reception_required
def delete_inventory_item(item_id):
    """Delete an inventory item (soft delete by setting inactive)"""
    try:
        user_id = session.get('user_id')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if item exists
            cursor.execute(
                "SELECT id, name FROM inventory_items WHERE id = ?", (item_id,))
            item = cursor.fetchone()

            if not item:
                return jsonify({'error': 'Item not found'}), 404

            # Soft delete by setting inactive
            cursor.execute("""
                UPDATE inventory_items 
                SET is_active = 0, updated_at = datetime('now')
                WHERE id = ?
            """, (item_id,))

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, old_data)
                VALUES (?, 'DELETE_INVENTORY_ITEM', 'inventory_items', ?, ?)
            """, (user_id, item_id, json.dumps(item)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Item deleted successfully'
        }), 200

    except Exception as e:
        print(f"Delete inventory item error: {e}")
        return jsonify({'error': 'Failed to delete item'}), 500


# =========================================
# Create Purchase Order
# =========================================

@reception_inventory_bp.route('/order', methods=['POST'])
@login_required
@reception_required
def create_purchase_order():
    """Create a purchase order and update inventory"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')

        items = data.get('items', [])
        supplier = data.get('supplier')
        order_date = data.get('order_date')
        delivery_date = data.get('delivery_date')
        reference = data.get('reference')
        payment_method = data.get('payment_method')
        notes = data.get('notes', '')

        if not items:
            return jsonify({'error': 'No items in order'}), 400

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Process each item in order
            for item in items:
                item_id = item.get('id')
                quantity = item.get('quantity', 0)

                if quantity <= 0:
                    continue

                # Update inventory stock
                cursor.execute("""
                    UPDATE inventory_items 
                    SET current_stock = current_stock + ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (quantity, item_id))

                # Log inventory transaction
                cursor.execute("""
                    INSERT INTO inventory_transactions (
                        item_id, type, quantity, transaction_date, 
                        reason, reference_number, staff_id, notes
                    ) VALUES (?, 'purchase', ?, ?, ?, ?, ?, ?)
                """, (
                    item_id, quantity, datetime.now(),
                    f"Purchase order: {reference}", reference, user_id, notes
                ))

            # Log the order creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_PURCHASE_ORDER', 'inventory_transactions', NULL, ?)
            """, (user_id, json.dumps({
                'supplier': supplier,
                'reference': reference,
                'items': items,
                'total': data.get('total', 0)
            })))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Purchase order created successfully',
            'reference': reference
        }), 201

    except Exception as e:
        print(f"Create purchase order error: {e}")
        return jsonify({'error': 'Failed to create order'}), 500


# =========================================
# Get Categories
# =========================================

@reception_inventory_bp.route('/categories', methods=['GET'])
@login_required
@reception_required
def get_categories():
    """Get all inventory categories"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT category 
                FROM inventory_items 
                WHERE is_active = 1 AND category IS NOT NULL
                ORDER BY category
            """)
            categories = [row['category'] for row in cursor.fetchall()]

        db.close()
        return jsonify({'success': True, 'categories': categories}), 200

    except Exception as e:
        print(f"Get categories error: {e}")
        return jsonify({'error': 'Failed to fetch categories'}), 500


# =========================================
# Get Suppliers (for dropdown)
# =========================================

@reception_inventory_bp.route('/suppliers', methods=['GET'])
@login_required
@reception_required
def get_suppliers():
    """Get list of suppliers (from inventory or separate table)"""
    try:
        # For now, return default suppliers list
        # In production, you'd have a suppliers table
        suppliers = [
            {'id': 1, 'name': 'MedPlus Pharmaceuticals'},
            {'id': 2, 'name': 'HealthCare Distributors'},
            {'id': 3, 'name': 'Dental Supply Co.'},
            {'id': 4, 'name': 'Global Medical Solutions'}
        ]

        return jsonify({'success': True, 'suppliers': suppliers}), 200

    except Exception as e:
        print(f"Get suppliers error: {e}")
        return jsonify({'error': 'Failed to fetch suppliers'}), 500


# =========================================
# Get Transaction History
# =========================================

@reception_inventory_bp.route('/transactions', methods=['GET'])
@login_required
@reception_required
def get_transactions():
    """Get inventory transaction history"""
    try:
        item_id = request.args.get('item_id', type=int)
        limit = request.args.get('limit', 20, type=int)

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        transactions = []

        with db.cursor() as cursor:
            query = """
                SELECT 
                    it.id,
                    it.type,
                    it.quantity,
                    it.transaction_date,
                    it.reason,
                    it.reference_number,
                    it.notes,
                    i.name as item_name
                FROM inventory_transactions it
                JOIN inventory_items i ON it.item_id = i.id
            """
            params = []

            if item_id:
                query += " WHERE it.item_id = ?"
                params.append(item_id)

            query += " ORDER BY it.transaction_date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                transactions.append({
                    'id': row['id'],
                    'type': row['type'],
                    'quantity': row['quantity'],
                    'date': row['transaction_date'].strftime('%Y-%m-%d %H:%M:%S') if row['transaction_date'] else '',
                    'reason': row['reason'],
                    'reference': row['reference_number'],
                    'notes': row['notes'],
                    'item_name': row['item_name']
                })

        db.close()
        return jsonify({'success': True, 'transactions': transactions}), 200

    except Exception as e:
        print(f"Get transactions error: {e}")
        return jsonify({'error': 'Failed to fetch transactions'}), 500
