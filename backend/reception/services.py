import sqlite3
# =========================================
# Perfections Dental Services
# Reception Services Module - v1.0
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


# Create reception services blueprint (different name to avoid conflict)
reception_services_bp = Blueprint(
    'reception_services', __name__, url_prefix='/api/reception/services')



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
# Get All Services
# =========================================

@reception_services_bp.route('/', methods=['GET'])
@login_required
@reception_required
def get_services():
    """Get all services with pagination and filtering"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 12))
        search = request.args.get('search', '')
        category_filter = request.args.get('category', 'all')

        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        services = []

        with db.cursor() as cursor:
            # Build query
            query = """
                SELECT 
                    s.id,
                    s.name,
                    s.price,
                    s.duration_minutes,
                    s.description,
                    s.code,
                    s.tax_rate,
                    s.is_active,
                    s.is_emergency,
                    s.emergency_priority,
                    s.color,
                    s.created_at,
                    sc.id as category_id,
                    sc.name as category_name,
                    sc.color as category_color,
                    sc.description as category_description
                FROM services s
                LEFT JOIN service_categories sc ON s.category_id = sc.id
                WHERE 1=1
            """
            params = []

            if search:
                query += """ AND (
                    s.name LIKE ? OR 
                    s.code LIKE ? OR 
                    s.description LIKE ? OR
                    sc.name LIKE ?
                )"""
                search_term = f"%{search}%"
                params.extend([search_term, search_term,
                              search_term, search_term])

            if category_filter != 'all':
                query += " AND sc.name = ?"
                params.append(category_filter)

            # Count total
            count_query = f"SELECT COUNT(*) as total FROM ({query}) as subquery"
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()['total']

            # Add sorting and pagination
            query += " ORDER BY s.created_at DESC LIMIT ? OFFSET ?"
            params.extend([per_page, (page - 1) * per_page])

            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

            for row in results:
                services.append({
                    'id': row['id'],
                    'name': row['name'],
                    'price': float(row['price']),
                    'duration': row['duration_minutes'] or 30,
                    'description': row['description'],
                    'code': row['code'],
                    'tax_rate': float(row['tax_rate']) if row['tax_rate'] else 0,
                    'is_active': bool(row['is_active']),
                    'is_emergency': bool(row['is_emergency']),
                    'emergency_priority': row['emergency_priority'],
                    'color': row['color'] or '#0066cc',
                    'category': {
                        'id': row['category_id'],
                        'name': row['category_name'],
                        'color': row['category_color'],
                        'description': row['category_description']
                    } if row['category_id'] else None,
                    'created_at': row['created_at'].strftime('%Y-%m-%d') if row['created_at'] else ''
                })

        db.close()

        return jsonify({
            'success': True,
            'services': services,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page if total_count > 0 else 1
        }), 200

    except Exception as e:
        print(f"Get services error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch services'}), 500


# =========================================
# Get Service Categories
# =========================================

@reception_services_bp.route('/categories', methods=['GET'])
@login_required
@reception_required
def get_categories():
    """Get all service categories"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        categories = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    sc.id,
                    sc.name,
                    sc.color,
                    sc.description,
                    COUNT(s.id) as service_count
                FROM service_categories sc
                LEFT JOIN services s ON sc.id = s.category_id AND s.is_active = 1
                GROUP BY sc.id
                ORDER BY sc.name
            """)

            results = cursor.fetchall()

            for row in results:
                categories.append({
                    'id': row['id'],
                    'name': row['name'],
                    'color': row['color'] or '#0066cc',
                    'description': row['description'],
                    'service_count': row['service_count']
                })

        db.close()
        return jsonify({'success': True, 'categories': categories}), 200

    except Exception as e:
        print(f"Get categories error: {e}")
        return jsonify({'error': 'Failed to fetch categories'}), 500


# =========================================
# Get Single Service
# =========================================

@reception_services_bp.route('/<int:service_id>', methods=['GET'])
@login_required
@reception_required
def get_service(service_id):
    """Get single service details"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    s.id,
                    s.name,
                    s.price,
                    s.duration_minutes,
                    s.description,
                    s.code,
                    s.tax_rate,
                    s.is_active,
                    s.is_emergency,
                    s.emergency_priority,
                    s.color,
                    sc.id as category_id,
                    sc.name as category_name,
                    sc.color as category_color
                FROM services s
                LEFT JOIN service_categories sc ON s.category_id = sc.id
                WHERE s.id = ?
            """, (service_id,))

            service = cursor.fetchone()

            if not service:
                return jsonify({'error': 'Service not found'}), 404

            result = {
                'id': service['id'],
                'name': service['name'],
                'price': float(service['price']),
                'duration': service['duration_minutes'] or 30,
                'description': service['description'],
                'code': service['code'],
                'tax_rate': float(service['tax_rate']) if service['tax_rate'] else 0,
                'is_active': bool(service['is_active']),
                'is_emergency': bool(service['is_emergency']),
                'emergency_priority': service['emergency_priority'],
                'color': service['color'] or '#0066cc',
                'category': {
                    'id': service['category_id'],
                    'name': service['category_name'],
                    'color': service['category_color']
                } if service['category_id'] else None
            }

        db.close()
        return jsonify({'success': True, 'service': result}), 200

    except Exception as e:
        print(f"Get service error: {e}")
        return jsonify({'error': 'Failed to fetch service'}), 500


# =========================================
# Create Service
# =========================================

@reception_services_bp.route('/', methods=['POST'])
@login_required
@reception_required
def create_service():
    """Create a new service"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get category id
            category_id = None
            if data.get('category_name'):
                cursor.execute(
                    "SELECT id FROM service_categories WHERE name = ?", (data.get('category_name'),))
                category = cursor.fetchone()
                if category:
                    category_id = category['id']

            # Insert service
            cursor.execute("""
                INSERT INTO services (
                    category_id, name, price, duration_minutes, description,
                    code, tax_rate, is_active, is_emergency, emergency_priority, color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                category_id,
                data.get('name'),
                data.get('price'),
                data.get('duration'),
                data.get('description'),
                data.get('code'),
                data.get('tax_rate', 0),
                data.get('is_active', True),
                data.get('is_emergency', False),
                data.get('emergency_priority'),
                data.get('color', '#0066cc')
            ))

            service_id = cursor.lastrowid

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_SERVICE', 'services', ?, ?)
            """, (session['user_id'], service_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Service created successfully',
            'service_id': service_id
        }), 201

    except Exception as e:
        print(f"Create service error: {e}")
        return jsonify({'error': 'Failed to create service'}), 500


# =========================================
# Update Service
# =========================================

@reception_services_bp.route('/<int:service_id>', methods=['PUT'])
@login_required
@reception_required
def update_service(service_id):
    """Update a service"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if service exists
            cursor.execute(
                "SELECT id FROM services WHERE id = ?", (service_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Service not found'}), 404

            # Get category id
            category_id = None
            if data.get('category_name'):
                cursor.execute(
                    "SELECT id FROM service_categories WHERE name = ?", (data.get('category_name'),))
                category = cursor.fetchone()
                if category:
                    category_id = category['id']

            # Update service
            cursor.execute("""
                UPDATE services SET
                    category_id = ?,
                    name = ?,
                    price = ?,
                    duration_minutes = ?,
                    description = ?,
                    code = ?,
                    tax_rate = ?,
                    is_active = ?,
                    is_emergency = ?,
                    emergency_priority = ?,
                    color = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                category_id,
                data.get('name'),
                data.get('price'),
                data.get('duration'),
                data.get('description'),
                data.get('code'),
                data.get('tax_rate', 0),
                data.get('is_active', True),
                data.get('is_emergency', False),
                data.get('emergency_priority'),
                data.get('color', '#0066cc'),
                service_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_SERVICE', 'services', ?, ?)
            """, (session['user_id'], service_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Service updated successfully'}), 200

    except Exception as e:
        print(f"Update service error: {e}")
        return jsonify({'error': 'Failed to update service'}), 500


# =========================================
# Delete/Deactivate Service
# =========================================

@reception_services_bp.route('/<int:service_id>', methods=['DELETE'])
@login_required
@reception_required
def delete_service(service_id):
    """Delete or deactivate a service"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if service has been used in appointments
            cursor.execute(
                "SELECT COUNT(*) as count FROM appointment_services WHERE service_id = ?", (service_id,))
            usage = cursor.fetchone()

            if usage['count'] > 0:
                # Mark as inactive instead of deleting
                cursor.execute("""
                    UPDATE services SET is_active = 0, updated_at = datetime('now')
                    WHERE id = ?
                """, (service_id,))
                message = "Service marked as inactive (has been used in appointments)"
            else:
                # Delete service
                cursor.execute(
                    "DELETE FROM services WHERE id = ?", (service_id,))
                message = "Service deleted successfully"

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_SERVICE', 'services', ?)
            """, (session['user_id'], service_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': message}), 200

    except Exception as e:
        print(f"Delete service error: {e}")
        return jsonify({'error': 'Failed to delete service'}), 500


# =========================================
# Create Category
# =========================================

@reception_services_bp.route('/categories', methods=['POST'])
@login_required
@reception_required
def create_category():
    """Create a new service category"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO service_categories (name, color, description)
                VALUES (?, ?, ?)
            """, (
                data.get('name'),
                data.get('color', '#0066cc'),
                data.get('description')
            ))

            category_id = cursor.lastrowid

            # Log creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'CREATE_CATEGORY', 'service_categories', ?, ?)
            """, (session['user_id'], category_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Category created successfully',
            'category_id': category_id
        }), 201

    except Exception as e:
        print(f"Create category error: {e}")
        return jsonify({'error': 'Failed to create category'}), 500


# =========================================
# Update Category
# =========================================

@reception_services_bp.route('/categories/<int:category_id>', methods=['PUT'])
@login_required
@reception_required
def update_category(category_id):
    """Update a service category"""
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE service_categories SET
                    name = ?,
                    color = ?,
                    description = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                data.get('name'),
                data.get('color', '#0066cc'),
                data.get('description'),
                category_id
            ))

            # Log update
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'UPDATE_CATEGORY', 'service_categories', ?, ?)
            """, (session['user_id'], category_id, json.dumps(data)))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Category updated successfully'}), 200

    except Exception as e:
        print(f"Update category error: {e}")
        return jsonify({'error': 'Failed to update category'}), 500


# =========================================
# Delete Category
# =========================================

@reception_services_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@login_required
@reception_required
def delete_category(category_id):
    """Delete a category (if no services linked)"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if category has services
            cursor.execute(
                "SELECT COUNT(*) as count FROM services WHERE category_id = ?", (category_id,))
            services_count = cursor.fetchone()

            if services_count['count'] > 0:
                return jsonify({'error': 'Cannot delete category with existing services'}), 400

            cursor.execute(
                "DELETE FROM service_categories WHERE id = ?", (category_id,))

            # Log deletion
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id)
                VALUES (?, 'DELETE_CATEGORY', 'service_categories', ?)
            """, (session['user_id'], category_id))

            db.commit()

        db.close()
        return jsonify({'success': True, 'message': 'Category deleted successfully'}), 200

    except Exception as e:
        print(f"Delete category error: {e}")
        return jsonify({'error': 'Failed to delete category'}), 500


# =========================================
# Get Stats
# =========================================

@reception_services_bp.route('/stats', methods=['GET'])
@login_required
@reception_required
def get_service_stats():
    """Get service statistics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        stats = {}

        with db.cursor() as cursor:
            # Total services
            cursor.execute("SELECT COUNT(*) as total FROM services")
            stats['total_services'] = cursor.fetchone()['total']

            # Active services
            cursor.execute(
                "SELECT COUNT(*) as total FROM services WHERE is_active = TRUE")
            stats['active_services'] = cursor.fetchone()['total']

            # Total categories
            cursor.execute("SELECT COUNT(*) as total FROM service_categories")
            stats['total_categories'] = cursor.fetchone()['total']

            # Average price
            cursor.execute("SELECT AVG(price) as avg_price FROM services")
            avg_price = cursor.fetchone()['avg_price']
            stats['avg_price'] = float(avg_price) if avg_price else 0

            # Emergency services
            cursor.execute(
                "SELECT COUNT(*) as total FROM services WHERE is_emergency = TRUE")
            stats['emergency_services'] = cursor.fetchone()['total']

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500


# =========================================
# Duplicate Service
# =========================================

@reception_services_bp.route('/<int:service_id>/duplicate', methods=['POST'])
@login_required
@reception_required
def duplicate_service(service_id):
    """Duplicate a service"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Get original service
            cursor.execute("""
                SELECT * FROM services WHERE id = ?
            """, (service_id,))
            original = cursor.fetchone()

            if not original:
                return jsonify({'error': 'Service not found'}), 404

            # Create duplicate
            cursor.execute("""
                INSERT INTO services (
                    category_id, name, price, duration_minutes, description,
                    code, tax_rate, is_active, is_emergency, emergency_priority, color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                original['category_id'],
                f"{original['name']} (Copy)",
                original['price'],
                original['duration_minutes'],
                original['description'],
                f"{original['code']}-COPY" if original['code'] else None,
                original['tax_rate'],
                original['is_active'],
                original['is_emergency'],
                original['emergency_priority'],
                original['color']
            ))

            new_service_id = cursor.lastrowid

            # Log duplication
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, table_name, record_id, new_data)
                VALUES (?, 'DUPLICATE_SERVICE', 'services', ?, ?)
            """, (session['user_id'], new_service_id, json.dumps({'original_id': service_id})))

            db.commit()

        db.close()
        return jsonify({
            'success': True,
            'message': 'Service duplicated successfully',
            'service_id': new_service_id
        }), 201

    except Exception as e:
        print(f"Duplicate service error: {e}")
        return jsonify({'error': 'Failed to duplicate service'}), 500
