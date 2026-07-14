import sqlite3
# =========================================
# Perfections Dental Services
# Services Management Module - v1.0
# SuperAdmin Only
# =========================================

from config import Config
from db import get_db
from auth import login_required, role_required
from flask import Blueprint, jsonify, session, request
from datetime import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

services_bp = Blueprint('services', __name__,
                        url_prefix='/api/superadmin/services')



# =========================================
# Get All Services
# =========================================


@services_bp.route('/', methods=['GET'])
@login_required
@role_required('superadmin')
def get_services():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        services = []
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT s.*, sc.name as category_name, sc.color as category_color
                FROM services s
                LEFT JOIN service_categories sc ON s.category_id = sc.id
                ORDER BY s.name
            """)
            results = cursor.fetchall()
            for row in results:
                services.append({
                    'id': row['id'],
                    'name': row['name'],
                    'category_id': row['category_id'],
                    'category': row['category_name'],
                    'price': float(row['price']),
                    'duration_minutes': row['duration_minutes'],
                    'description': row['description'],
                    'code': row['code'],
                    'tax_rate': float(row['tax_rate']),
                    'is_active': row['is_active'],
                    'is_emergency': row['is_emergency'],
                    'emergency_priority': row['emergency_priority'],
                    'color': row['color']
                })
        db.close()
        return jsonify({'success': True, 'services': services}), 200
    except Exception as e:
        print(f"Get services error: {e}")
        return jsonify({'error': 'Failed to fetch services'}), 500

# =========================================
# Get Service Categories
# =========================================


@services_bp.route('/categories', methods=['GET'])
@login_required
@role_required('superadmin')
def get_categories():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT sc.*, COUNT(s.id) as service_count
                FROM service_categories sc
                LEFT JOIN services s ON sc.id = s.category_id
                GROUP BY sc.id
                ORDER BY sc.name
            """)
            categories = cursor.fetchall()
            for cat in categories:
                cat['service_count'] = cat['service_count'] or 0
        db.close()
        return jsonify({'success': True, 'categories': categories}), 200
    except Exception as e:
        print(f"Get categories error: {e}")
        return jsonify({'error': 'Failed to fetch categories'}), 500

# =========================================
# Create Service
# =========================================


@services_bp.route('/', methods=['POST'])
@login_required
@role_required('superadmin')
def create_service():
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO services (name, category_id, price, duration_minutes, description, 
                    code, tax_rate, is_active, is_emergency, emergency_priority, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('name'),
                data.get('category_id'),
                data.get('price'),
                data.get('duration_minutes'),
                data.get('description'),
                data.get('code'),
                data.get('tax_rate', 0),
                data.get('is_active', True),
                data.get('is_emergency', False),
                data.get('emergency_priority'),
                data.get('color', '#0066cc')
            ))
            service_id = cursor.lastrowid
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Service created successfully', 'service_id': service_id}), 201
    except Exception as e:
        print(f"Create service error: {e}")
        return jsonify({'error': 'Failed to create service'}), 500

# =========================================
# Update Service
# =========================================


@services_bp.route('/<int:service_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_service(service_id):
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE services SET
                    name = ?,
                    category_id = ?,
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
                data.get('name'),
                data.get('category_id'),
                data.get('price'),
                data.get('duration_minutes'),
                data.get('description'),
                data.get('code'),
                data.get('tax_rate', 0),
                data.get('is_active', True),
                data.get('is_emergency', False),
                data.get('emergency_priority'),
                data.get('color', '#0066cc'),
                service_id
            ))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Service updated successfully'}), 200
    except Exception as e:
        print(f"Update service error: {e}")
        return jsonify({'error': 'Failed to update service'}), 500

# =========================================
# Delete Service
# =========================================


@services_bp.route('/<int:service_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_service(service_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("DELETE FROM services WHERE id = ?", (service_id,))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Service deleted successfully'}), 200
    except Exception as e:
        print(f"Delete service error: {e}")
        return jsonify({'error': 'Failed to delete service'}), 500

# =========================================
# Duplicate Service
# =========================================


@services_bp.route('/<int:service_id>/duplicate', methods=['POST'])
@login_required
@role_required('superadmin')
def duplicate_service(service_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM services WHERE id = ?", (service_id,))
            service = cursor.fetchone()
            if not service:
                return jsonify({'error': 'Service not found'}), 404

            cursor.execute("""
                INSERT INTO services (name, category_id, price, duration_minutes, description, 
                    code, tax_rate, is_active, is_emergency, emergency_priority, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{service['name']} (Copy)",
                service['category_id'],
                service['price'],
                service['duration_minutes'],
                service['description'],
                f"{service['code']}-COPY" if service['code'] else None,
                service['tax_rate'],
                service['is_active'],
                service['is_emergency'],
                service['emergency_priority'],
                service['color']
            ))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Service duplicated successfully'}), 201
    except Exception as e:
        print(f"Duplicate service error: {e}")
        return jsonify({'error': 'Failed to duplicate service'}), 500

# =========================================
# Create Category
# =========================================


@services_bp.route('/categories', methods=['POST'])
@login_required
@role_required('superadmin')
def create_category():
    try:
        data = request.get_json()
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO service_categories (name, color, description)
                VALUES (?, ?, ?)
            """, (data.get('name'), data.get('color', '#0066cc'), data.get('description')))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Category created successfully'}), 201
    except Exception as e:
        print(f"Create category error: {e}")
        return jsonify({'error': 'Failed to create category'}), 500

# =========================================
# Update Category
# =========================================


@services_bp.route('/categories/<int:category_id>', methods=['PUT'])
@login_required
@role_required('superadmin')
def update_category(category_id):
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
                    description = ?
                WHERE id = ?
            """, (data.get('name'), data.get('color', '#0066cc'), data.get('description'), category_id))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Category updated successfully'}), 200
    except Exception as e:
        print(f"Update category error: {e}")
        return jsonify({'error': 'Failed to update category'}), 500

# =========================================
# Delete Category
# =========================================


@services_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@login_required
@role_required('superadmin')
def delete_category(category_id):
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            # Check if category has services
            cursor.execute(
                "SELECT COUNT(*) as count FROM services WHERE category_id = ?", (category_id,))
            result = cursor.fetchone()
            if result['count'] > 0:
                return jsonify({'error': 'Cannot delete category with existing services'}), 400

            cursor.execute(
                "DELETE FROM service_categories WHERE id = ?", (category_id,))
            db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Category deleted successfully'}), 200
    except Exception as e:
        print(f"Delete category error: {e}")
        return jsonify({'error': 'Failed to delete category'}), 500

# =========================================
# Get Dashboard Stats
# =========================================


@services_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_stats():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM services")
            total_services = cursor.fetchone()['total']

            cursor.execute(
                "SELECT COUNT(*) as total FROM services WHERE is_active = TRUE")
            active_services = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as total FROM service_categories")
            total_categories = cursor.fetchone()['total']

            cursor.execute(
                "SELECT AVG(price) as avg FROM services WHERE is_active = TRUE")
            avg_price = cursor.fetchone()['avg'] or 0

        db.close()
        return jsonify({
            'success': True,
            'stats': {
                'total_services': total_services,
                'active_services': active_services,
                'total_categories': total_categories,
                'avg_price': float(avg_price)
            }
        }), 200
    except Exception as e:
        print(f"Get stats error: {e}")
        return jsonify({'error': 'Failed to fetch stats'}), 500

# =========================================
# Export Services
# =========================================


@services_bp.route('/export', methods=['GET'])
@login_required
@role_required('superadmin')
def export_services():
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT s.name, sc.name as category, s.price, s.duration_minutes, s.description, 
                       s.code, s.tax_rate, s.is_active, s.is_emergency
                FROM services s
                LEFT JOIN service_categories sc ON s.category_id = sc.id
                ORDER BY s.name
            """)
            services = cursor.fetchall()

        # Create CSV
        import csv
        from io import StringIO
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Name', 'Category', 'Price', 'Duration (min)',
                        'Description', 'Code', 'Tax Rate (%)', 'Active', 'Emergency'])
        for s in services:
            writer.writerow([
                s['name'], s['category'], s['price'], s['duration_minutes'],
                s['description'], s['code'], s['tax_rate'],
                'Yes' if s['is_active'] else 'No',
                'Yes' if s['is_emergency'] else 'No'
            ])

        db.close()
        return jsonify({'success': True, 'csv': output.getvalue()}), 200
    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({'error': 'Failed to export'}), 500
