import sqlite3
# =========================================
# Perfections Dental Services
# Inventory Management Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Create inventory blueprint
inventory_bp = Blueprint('inventory', __name__,
                         url_prefix='/api/superadmin/inventory')



# =========================================
# Get All Inventory Items
# =========================================

@inventory_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_inventory():
    """Get all inventory items"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        items = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, name, category, manufacturer, unit, price,
                    current_stock, min_threshold, max_stock, location,
                    expiry_date, batch_number, requires_prescription,
                    is_active, description, notes, created_at, updated_at
                FROM inventory_items
                WHERE is_active = 1
                ORDER BY name
            """)

            rows = cursor.fetchall()

            for row in rows:
                # Calculate stock status
                stock = row['current_stock']
                threshold = row['min_threshold']

                if stock <= threshold * 0.3:
                    stock_status = 'critical'
                    stock_badge = 'error'
                    stock_label = 'Critical Low'
                elif stock <= threshold:
                    stock_status = 'low'
                    stock_badge = 'warning'
                    stock_label = 'Low Stock'
                else:
                    stock_status = 'good'
                    stock_badge = 'success'
                    stock_label = 'In Stock'

                # Calculate expiry status
                today = datetime.now().date()
                if row['expiry_date']:
                    expiry = row['expiry_date']
                    days_left = (expiry - today).days

                    if days_left <= 15:
                        expiry_status = 'critical'
                    elif days_left <= 30:
                        expiry_status = 'warning'
                    else:
                        expiry_status = 'safe'
                else:
                    expiry_status = 'safe'
                    days_left = None

                items.append({
                    'id': row['id'],
                    'name': row['name'],
                    'category': row['category'] or 'Uncategorized',
                    'type': 'Medication' if row['category'] in ['Antibiotics', 'Analgesics', 'Anesthetics', 'Mouthwash'] else 'Supply',
                    'stock': stock,
                    'unit': row['unit'] or 'units',
                    'threshold': threshold,
                    'maxStock': row['max_stock'] or 200,
                    'price': float(row['price']) if row['price'] else 0,
                    'manufacturer': row['manufacturer'] or '',
                    'expiry': row['expiry_date'].strftime('%Y-%m-%d') if row['expiry_date'] else '',
                    'batch': row['batch_number'] or '',
                    'description': row['description'] or '',
                    'location': row['location'] or '',
                    'requires_prescription': row['requires_prescription'] or False,
                    'active': row['is_active'],
                    'stock_status': stock_status,
                    'stock_badge': stock_badge,
                    'stock_label': stock_label,
                    'expiry_status': expiry_status,
                    'days_left': days_left,
                    'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else '',
                    'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row['updated_at'] else ''
                })

        db.close()
        return jsonify({'success': True, 'items': items}), 200

    except Exception as e:
        print(f"Get inventory error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch inventory'}), 500


# =========================================
# Get Single Inventory Item
# =========================================

@inventory_bp.route('/<int:item_id>', methods=['GET'])
@login_required
@role_required('superadmin')
def get_inventory_item(item_id):
    """Get single inventory item details"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, name, category, manufacturer, unit, price,
                    current_stock, min_threshold, max_stock, location,
                    expiry_date, batch_number, requires_prescription,
                    is_active, description, notes
                FROM inventory_items
                WHERE id = ?
            """, (item_id,))

            row = cursor.fetchone()

            if not row:
                return jsonify({'error': 'Item not found'}), 404

            item = {
                'id': row['id'],
                'name': row['name'],
                'category': row['category'] or '',
                'manufacturer': row['manufacturer'] or '',
                'unit': row['unit'] or 'units',
                'price': float(row['price']) if row['price'] else 0,
                'stock': row['current_stock'],
                'threshold': row['min_threshold'],
                'max_stock': row['max_stock'] or 200,
                'location': row['location'] or '',
                'expiry': row['expiry_date'].strftime('%Y-%m-%d') if row['expiry_date'] else '',
                'batch': row['batch_number'] or '',
                'requires_prescription': row['requires_prescription'] or False,
                'active': row['is_active'],
                'description': row['description'] or '',
                'notes': row['notes'] or ''
            }

        db.close()
        return jsonify({'success': True, 'item': item}), 200

    except Exception as e:
        print(f"Get inventory item error: {e}")
        return jsonify({'error': 'Failed to fetch item'}), 500


# =========================================
# Create Inventory Item
# =========================================

@inventory_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_inventory_item():
    """Create a new inventory item"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Insert new inventory item
            cursor.execute("""
                INSERT INTO inventory_items (
                    name, category, manufacturer, unit, price,
                    current_stock, min_threshold, max_stock, location,
                    expiry_date, batch_number, requires_prescription,
                    is_active, description, notes
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                data.get('name'),
                data.get('category'),
                data.get('manufacturer'),
                data.get('unit', 'units'),
                data.get('price', 0),
                data.get('stock', 0),
                data.get('threshold', 20),
                data.get('max_stock', 200),
                data.get('location'),
                data.get('expiry') if data.get('expiry') else None,
                data.get('batch'),
                data.get('requires_prescription', False),
                data.get('active', True),
                data.get('description'),
                data.get('notes')
            ))

            item_id = cursor.lastrowid

            # Record initial stock transaction
            if data.get('stock', 0) > 0:
                cursor.execute("""
                    INSERT INTO inventory_transactions (
                        item_id, type, quantity, transaction_date, reason, staff_id
                    ) VALUES (
                        ?, 'purchase', ?, datetime('now'), ?, ?
                    )
                """, (item_id, data.get('stock'), 'Initial stock', session['user_id']))

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE', 'inventory_items', ?, ?)
            """, (session['user_id'], item_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Inventory item created successfully',
            'item_id': item_id
        }), 201

    except Exception as e:
        print(f"Create inventory item error: {e}")
        return jsonify({'error': 'Failed to create inventory item'}), 500


# =========================================
# Update Inventory Item
# =========================================

@inventory_bp.route('/<int:item_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_inventory_item(item_id):
    """Update inventory item details"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if item exists
            cursor.execute(
                "SELECT id FROM inventory_items WHERE id = ?", (item_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Item not found'}), 404

            # Update inventory item
            cursor.execute("""
                UPDATE inventory_items SET
                    name = ?,
                    category = ?,
                    manufacturer = ?,
                    unit = ?,
                    price = ?,
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
                data.get('unit', 'units'),
                data.get('price', 0),
                data.get('threshold', 20),
                data.get('max_stock', 200),
                data.get('location'),
                data.get('expiry') if data.get('expiry') else None,
                data.get('batch'),
                data.get('requires_prescription', False),
                data.get('active', True),
                data.get('description'),
                data.get('notes'),
                item_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE', 'inventory_items', ?, ?)
            """, (session['user_id'], item_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Inventory item updated successfully'
        }), 200

    except Exception as e:
        print(f"Update inventory item error: {e}")
        return jsonify({'error': 'Failed to update inventory item'}), 500


# =========================================
# Delete Inventory Item
# =========================================

@inventory_bp.route('/<int:item_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_inventory_item(item_id):
    """Delete inventory item (soft delete)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Soft delete - mark as inactive
            cursor.execute("""
                UPDATE inventory_items SET is_active = 0, updated_at = datetime('now')
                WHERE id = ?
            """, (item_id,))

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE', 'inventory_items', ?)
            """, (session['user_id'], item_id))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Inventory item deleted successfully'
        }), 200

    except Exception as e:
        print(f"Delete inventory item error: {e}")
        return jsonify({'error': 'Failed to delete inventory item'}), 500


# =========================================
# Adjust Stock
# =========================================

@inventory_bp.route('/<int:item_id>/stock', methods=['POST'])
@login_required
@role_required('superadmin')
def adjust_stock(item_id):
    """Adjust inventory stock level"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        adjustment_type = data.get('type')  # 'add', 'remove', 'set'
        quantity = data.get('quantity', 0)
        reason = data.get('reason', '')
        reference = data.get('reference', '')

        if quantity <= 0:
            return jsonify({'error': 'Invalid quantity'}), 400

        with db.cursor() as cursor:
            # Get current stock
            cursor.execute(
                "SELECT current_stock FROM inventory_items WHERE id = ?", (item_id,))
            result = cursor.fetchone()
            if not result:
                return jsonify({'error': 'Item not found'}), 404

            current_stock = result['current_stock']
            new_stock = current_stock

            transaction_type = ''
            actual_quantity = quantity

            if adjustment_type == 'add':
                new_stock = current_stock + quantity
                transaction_type = 'purchase'
                actual_quantity = quantity
            elif adjustment_type == 'remove':
                if quantity > current_stock:
                    return jsonify({'error': 'Insufficient stock'}), 400
                new_stock = current_stock - quantity
                transaction_type = 'usage'
                actual_quantity = -quantity
            elif adjustment_type == 'set':
                actual_quantity = quantity - current_stock
                if actual_quantity > 0:
                    transaction_type = 'purchase'
                elif actual_quantity < 0:
                    transaction_type = 'usage'
                else:
                    transaction_type = 'adjustment'
                new_stock = quantity
            else:
                return jsonify({'error': 'Invalid adjustment type'}), 400

            # Update stock
            cursor.execute("""
                UPDATE inventory_items SET current_stock = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (new_stock, item_id))

            # Record transaction
            cursor.execute("""
                INSERT INTO inventory_transactions (
                    item_id, type, quantity, transaction_date, reason, reference_number, staff_id
                ) VALUES (
                    ?, ?, ?, datetime('now'), ?, ?, ?
                )
            """, (item_id, transaction_type, actual_quantity, reason, reference, session['user_id']))

            # Log adjustment
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'STOCK_ADJUST', 'inventory_items', ?, ?)
            """, (session['user_id'], item_id, json.dumps(data)))

            db.commit()

        db.close()

        return jsonify({
            'success': True,
            'message': 'Stock adjusted successfully',
            'new_stock': new_stock
        }), 200

    except Exception as e:
        print(f"Adjust stock error: {e}")
        return jsonify({'error': 'Failed to adjust stock'}), 500


# =========================================
# Get Stock History
# =========================================

@inventory_bp.route('/<int:item_id>/history', methods=['GET'])
@login_required
@role_required('superadmin')
def get_stock_history(item_id):
    """Get stock transaction history for an item"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        history = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    it.id, it.type, it.quantity, it.transaction_date,
                    it.reason, it.reference_number, it.notes,
                    u.first_name, u.last_name
                FROM inventory_transactions it
                LEFT JOIN users u ON it.staff_id = u.id
                WHERE it.item_id = ?
                ORDER BY it.transaction_date DESC
                LIMIT 50
            """, (item_id,))

            rows = cursor.fetchall()

            for row in rows:
                history.append({
                    'id': row['id'],
                    'type': row['type'],
                    'quantity': row['quantity'],
                    'date': row['transaction_date'].strftime('%Y-%m-%d %H:%M:%S') if row['transaction_date'] else '',
                    'reason': row['reason'] or '',
                    'reference': row['reference_number'] or '',
                    'staff': f"{row['first_name']} {row['last_name']}" if row['first_name'] else 'System'
                })

        db.close()
        return jsonify({'success': True, 'history': history}), 200

    except Exception as e:
        print(f"Get stock history error: {e}")
        return jsonify({'error': 'Failed to fetch stock history'}), 500


# =========================================
# Get Dashboard Stats
# =========================================

@inventory_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_inventory_stats():
    """Get inventory statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total items
            cursor.execute(
                "SELECT COUNT(*) as total FROM inventory_items WHERE is_active = TRUE")
            stats['total_items'] = cursor.fetchone()['total']

            # Categories count
            cursor.execute(
                "SELECT COUNT(DISTINCT category) as total FROM inventory_items WHERE category IS NOT NULL AND is_active = TRUE")
            stats['total_categories'] = cursor.fetchone()['total']

            # In stock items (above threshold)
            cursor.execute("""
                SELECT COUNT(*) as total FROM inventory_items 
                WHERE current_stock > min_threshold AND is_active = 1
            """)
            stats['in_stock'] = cursor.fetchone()['total']

            # Low stock items
            cursor.execute("""
                SELECT COUNT(*) as total FROM inventory_items 
                WHERE current_stock <= min_threshold AND is_active = 1
            """)
            stats['low_stock'] = cursor.fetchone()['total']

            # Expiring soon items (within 30 days)
            cursor.execute("""
                SELECT COUNT(*) as total FROM inventory_items 
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+30 days')
                AND is_active = 1
            """)
            stats['expiring_soon'] = cursor.fetchone()['total']

            # Calculate stock percentage
            if stats['total_items'] > 0:
                stats['stock_percentage'] = round(
                    (stats['in_stock'] / stats['total_items']) * 100, 1)
            else:
                stats['stock_percentage'] = 0

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get inventory stats error: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500


# =========================================
# Get Consumption Trends
# =========================================

@inventory_bp.route('/consumption', methods=['GET'])
@login_required
@role_required('superadmin')
def get_consumption_trends():
    """Get consumption trends for top items"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        trends = {}

        with db.cursor() as cursor:
            # Get top 5 most used items this month
            cursor.execute("""
                SELECT 
                    i.name,
                    SUM(CASE WHEN it.type = 'usage' THEN ABS(it.quantity) ELSE 0 END) as total_used
                FROM inventory_items i
                LEFT JOIN inventory_transactions it ON i.id = it.item_id
                WHERE CAST(strftime('%m', it.transaction_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', it.transaction_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                AND it.type = 'usage'
                GROUP BY i.id, i.name
                ORDER BY total_used DESC
                LIMIT 5
            """)

            top_items = cursor.fetchall()

            # Get total consumption value
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(it.quantity * i.price), 0) as total_value
                FROM inventory_transactions it
                JOIN inventory_items i ON it.item_id = i.id
                WHERE CAST(strftime('%m', it.transaction_date) AS INTEGER) = CAST(strftime('%m', date('now')) AS INTEGER)
                AND CAST(strftime('%Y', it.transaction_date) AS INTEGER) = CAST(strftime('%Y', date('now')) AS INTEGER)
                AND it.type = 'usage'
            """)
            total_consumption = cursor.fetchone()['total_value']

            # Get last month consumption for comparison
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(it.quantity * i.price), 0) as total_value
                FROM inventory_transactions it
                JOIN inventory_items i ON it.item_id = i.id
                WHERE CAST(strftime('%m', it.transaction_date) AS INTEGER) = CAST(strftime('%m', date(date('now'), '-1 months')) AS INTEGER)
                AND CAST(strftime('%Y', it.transaction_date) AS INTEGER) = CAST(strftime('%Y', date(date('now'), '-1 months')) AS INTEGER)
                AND it.type = 'usage'
            """)
            last_month_consumption = cursor.fetchone()['total_value']

            # Calculate trend percentage
            if last_month_consumption > 0:
                trend_percent = (
                    (total_consumption - last_month_consumption) / last_month_consumption) * 100
            else:
                trend_percent = 0

            trends['top_items'] = [
                {'name': item['name'], 'used': item['total_used']} for item in top_items]
            trends['total_consumption'] = float(total_consumption)
            trends['trend_percent'] = round(trend_percent, 1)
            trends['trend_direction'] = 'up' if trend_percent >= 0 else 'down'

        db.close()
        return jsonify({'success': True, 'trends': trends}), 200

    except Exception as e:
        print(f"Get consumption trends error: {e}")
        return jsonify({'error': 'Failed to fetch consumption trends'}), 500


# =========================================
# Get Expiry Calendar
# =========================================

@inventory_bp.route('/expiry-calendar', methods=['GET'])
@login_required
@role_required('superadmin')
def get_expiry_calendar():
    """Get items expiring soon"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        items = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, name, current_stock, unit, expiry_date,
                    CAST(julianday(expiry_date) - julianday(date('now')) AS INTEGER) as days_left
                FROM inventory_items
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+30 days')
                AND is_active = 1
                ORDER BY expiry_date ASC
            """)

            rows = cursor.fetchall()

            for row in rows:
                days_left = row['days_left']
                status = 'critical' if days_left <= 15 else 'warning'

                items.append({
                    'id': row['id'],
                    'name': row['name'],
                    'stock': row['current_stock'],
                    'unit': row['unit'] or 'units',
                    'expiry': row['expiry_date'].strftime('%Y-%m-%d') if row['expiry_date'] else '',
                    'days_left': days_left,
                    'status': status
                })

        db.close()
        return jsonify({'success': True, 'items': items}), 200

    except Exception as e:
        print(f"Get expiry calendar error: {e}")
        return jsonify({'error': 'Failed to fetch expiry calendar'}), 500


# =========================================
# Get Alerts
# =========================================

@inventory_bp.route('/alerts', methods=['GET'])
@login_required
@role_required('superadmin')
def get_alerts():
    """Get all inventory alerts (low stock and expiring soon)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        alerts = []

        with db.cursor() as cursor:
            # Low stock alerts
            cursor.execute("""
                SELECT 
                    id, name, category, current_stock, min_threshold,
                    'low_stock' as alert_type,
                    CASE 
                        WHEN current_stock <= min_threshold * 0.3 THEN 'critical'
                        ELSE 'warning'
                    END as severity
                FROM inventory_items
                WHERE current_stock <= min_threshold AND is_active = 1
            """)
            low_stock = cursor.fetchall()

            for item in low_stock:
                alerts.append({
                    'id': item['id'],
                    'name': item['name'],
                    'category': item['category'] or 'Uncategorized',
                    'type': 'low_stock',
                    'severity': item['severity'],
                    'stock': item['current_stock'],
                    'threshold': item['min_threshold'],
                    'percentage': round((item['current_stock'] / item['min_threshold']) * 100, 1)
                })

            # Expiring soon alerts
            cursor.execute("""
                SELECT 
                    id, name, category, expiry_date, unit,
                    CAST(julianday(expiry_date) - julianday(date('now')) AS INTEGER) as days_left,
                    CASE
                        WHEN CAST(julianday(expiry_date) - julianday(date('now')) AS INTEGER) <= 15 THEN 'critical'
                        ELSE 'warning'
                    END as severity
                FROM inventory_items
                WHERE expiry_date BETWEEN date('now') AND date(date('now'), '+30 days')
                AND is_active = 1
            """)
            expiring = cursor.fetchall()

            for item in expiring:
                alerts.append({
                    'id': item['id'],
                    'name': item['name'],
                    'category': item['category'] or 'Uncategorized',
                    'type': 'expiring',
                    'severity': item['severity'],
                    'expiry': item['expiry_date'].strftime('%Y-%m-%d') if item['expiry_date'] else '',
                    'days_left': item['days_left'],
                    'unit': item['unit'] or 'units'
                })

        db.close()
        return jsonify({'success': True, 'alerts': alerts}), 200

    except Exception as e:
        print(f"Get alerts error: {e}")
        return jsonify({'error': 'Failed to fetch alerts'}), 500
