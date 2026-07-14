import sqlite3
# =========================================
# Perfections Dental Services
# Analytics Module - v1.0
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


# Create analytics blueprint
analytics_bp = Blueprint('analytics', __name__,
                         url_prefix='/api/superadmin/analytics')



# =========================================
# Get Analytics Overview Stats
# =========================================


@analytics_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_analytics_stats():
    """Get overview statistics for analytics dashboard"""
    try:
        period = request.args.get('period', 'month')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Get date range
        today = datetime.now().date()
        if period == 'today':
            start_date = today
            end_date = today
            compare_start = today - timedelta(days=1)
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
            compare_start = start_date - timedelta(days=7)
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
            compare_start = (start_date - timedelta(days=1)).replace(day=1)
        elif period == 'quarter':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=quarter_month, day=1)
            end_date = today
            compare_start = (start_date - timedelta(days=1)).replace(day=1)
            compare_start = compare_start.replace(
                month=((compare_start.month - 1) // 3) * 3 + 1)
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
            compare_start = start_date.replace(year=start_date.year - 1)
        else:
            start_date = today
            end_date = today
            compare_start = today - timedelta(days=1)

        stats = {}

        with db.cursor() as cursor:
            # Total patients
            cursor.execute(
                "SELECT COUNT(*) as total FROM patients WHERE status = 'active'")
            stats['total_patients'] = cursor.fetchone()['total']

            # Total procedures (appointments with services)
            cursor.execute("""
                SELECT COUNT(DISTINCT a.id) as total
                FROM appointments a
                JOIN appointment_services ast ON a.id = ast.appointment_id
                WHERE a.appointment_date BETWEEN ? AND ?
            """, (start_date, end_date))
            stats['total_procedures'] = cursor.fetchone()['total']

            # New patients in period
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM patients
                WHERE registration_date BETWEEN ? AND ?
            """, (start_date, end_date))
            stats['new_patients'] = cursor.fetchone()['total']

            # New patients in previous period
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM patients
                WHERE registration_date BETWEEN ? AND ?
            """, (compare_start, start_date - timedelta(days=1)))
            previous_new = cursor.fetchone()['total']

            # Calculate new patient growth
            if previous_new > 0:
                stats['new_patients_growth'] = round(
                    ((stats['new_patients'] - previous_new) / previous_new) * 100, 1)
            else:
                stats['new_patients_growth'] = 100 if stats['new_patients'] > 0 else 0

            # Average rating (placeholder - you'd have a ratings table)
            stats['avg_rating'] = 4.8
            stats['rating_stars'] = 4.8

        db.close()
        return jsonify({'success': True, 'stats': stats}), 200

    except Exception as e:
        print(f"Analytics stats error: {e}")
        return jsonify({'error': 'Failed to fetch analytics stats'}), 500

# =========================================
# Get Peak Hours Analysis
# =========================================


@analytics_bp.route('/peak-hours', methods=['GET'])
@login_required
@role_required('superadmin')
def get_peak_hours():
    """Get peak hours analysis for appointments"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        peak_hours = []
        hour_ranges = [
            {'start': 8, 'end': 10, 'label': '8am - 10am'},
            {'start': 10, 'end': 12, 'label': '10am - 12pm'},
            {'start': 12, 'end': 14, 'label': '12pm - 2pm'},
            {'start': 14, 'end': 16, 'label': '2pm - 4pm'},
            {'start': 16, 'end': 18, 'label': '4pm - 6pm'}
        ]

        with db.cursor() as cursor:
            for hour_range in hour_ranges:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM appointments
                    WHERE CAST(strftime('%H', start_time) AS INTEGER) >= ? AND CAST(strftime('%H', start_time) AS INTEGER) < ?
                    AND appointment_date >= date(date('now'), '-30 days')
                """, (hour_range['start'], hour_range['end']))

                count = cursor.fetchone()['count']
                # Rough estimate
                utilization = min(100, round((count / 30 / 10) * 100))

                is_peak = hour_range['start'] == 10

                peak_hours.append({
                    'time': hour_range['label'],
                    'patients': count,
                    'utilization': utilization,
                    'is_peak': is_peak
                })

        # Add insight
        max_hour = max(peak_hours, key=lambda x: x['patients'])
        min_hour = min(peak_hours, key=lambda x: x['patients'])

        insight = f"Peak time is {max_hour['time']} with {max_hour['patients']} patients. Consider adding resources. Offer promotions for {min_hour['time']} slots to balance load."

        db.close()
        return jsonify({
            'success': True,
            'peak_hours': peak_hours,
            'insight': insight
        }), 200

    except Exception as e:
        print(f"Peak hours error: {e}")
        return jsonify({'error': 'Failed to fetch peak hours'}), 500

# =========================================
# Get Patient Demographics
# =========================================


@analytics_bp.route('/demographics', methods=['GET'])
@login_required
@role_required('superadmin')
def get_demographics():
    """Get patient demographics by age group"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        demographics = []

        with db.cursor() as cursor:
            # Age groups
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 0 AND 12 THEN '0-12 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 13 AND 25 THEN '13-25 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 26 AND 40 THEN '26-40 years'
                        WHEN ((julianday(date('now')) - julianday(dob)) / 365.25) BETWEEN 41 AND 60 THEN '41-60 years'
                        ELSE '60+ years'
                    END as age_group,
                    COUNT(*) as count
                FROM patients
                WHERE status = 'active'
                GROUP BY age_group
                ORDER BY 
                    CASE age_group
                        WHEN '0-12 years' THEN 1
                        WHEN '13-25 years' THEN 2
                        WHEN '26-40 years' THEN 3
                        WHEN '41-60 years' THEN 4
                        ELSE 5
                    END
            """)

            age_groups = cursor.fetchall()
            total = sum(g['count'] for g in age_groups)

            age_colors = ['#0066cc', '#34c759',
                          '#ff9500', '#9b59b6', '#ff6b6b']

            for i, group in enumerate(age_groups):
                percent = (group['count'] / total * 100) if total > 0 else 0
                demographics.append({
                    'label': group['age_group'],
                    'count': group['count'],
                    'percent': round(percent, 1),
                    'color': age_colors[i % len(age_colors)]
                })

            # Gender distribution
            cursor.execute("""
                SELECT 
                    gender,
                    COUNT(*) as count
                FROM patients
                WHERE status = 'active'
                GROUP BY gender
            """)
            gender_data = cursor.fetchall()

            gender_dist = {}
            for g in gender_data:
                gender_dist[g['gender']] = round(
                    (g['count'] / total * 100), 1) if total > 0 else 0

            # Patient type (new vs returning)
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN registration_date >= date(date('now'), '-30 days') THEN 1 END) as "new",
                    COUNT(CASE WHEN registration_date < date(date('now'), '-30 days') THEN 1 END) as "returning"
                FROM patients
                WHERE status = 'active'
            """)
            patient_types = cursor.fetchone()

            patient_type_dist = {
                'new': patient_types['new'],
                'returning': patient_types['returning'],
                'new_percent': round((patient_types['new'] / total * 100), 1) if total > 0 else 0,
                'returning_percent': round((patient_types['returning'] / total * 100), 1) if total > 0 else 0
            }

        db.close()

        # Generate pie chart data
        pie_data = []
        for demo in demographics:
            pie_data.append({
                'label': demo['label'],
                'value': demo['count'],
                'color': demo['color']
            })

        return jsonify({
            'success': True,
            'demographics': demographics,
            'pie_data': pie_data,
            'gender': gender_dist,
            'patient_types': patient_type_dist
        }), 200

    except Exception as e:
        print(f"Demographics error: {e}")
        return jsonify({'error': 'Failed to fetch demographics'}), 500

# =========================================
# Get Treatment Popularity
# =========================================


@analytics_bp.route('/treatments', methods=['GET'])
@login_required
@role_required('superadmin')
def get_treatment_popularity():
    """Get treatment popularity ranking"""
    try:
        period = request.args.get('period', 'quarter')
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        # Get date range
        today = datetime.now().date()
        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'quarter':
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=quarter_month, day=1)
            end_date = today
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            start_date = today - timedelta(days=30)
            end_date = today

        treatments = []

        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    s.id,
                    s.name,
                    COUNT(ast.id) as procedure_count,
                    COALESCE(SUM(ast.unit_price * ast.quantity), 0) as total_revenue,
                    AVG(ast.unit_price) as avg_price
                FROM services s
                LEFT JOIN appointment_services ast ON s.id = ast.service_id
                LEFT JOIN appointments a ON ast.appointment_id = a.id
                WHERE (a.appointment_date BETWEEN ? AND ? OR a.appointment_date IS NULL)
                AND s.is_active = 1
                GROUP BY s.id, s.name
                HAVING procedure_count > 0
                ORDER BY total_revenue DESC
                LIMIT 10
            """, (start_date, end_date))

            results = cursor.fetchall()

            max_count = results[0]['procedure_count'] if results else 1

            for i, t in enumerate(results):
                percent = (t['procedure_count'] / max_count *
                           100) if max_count > 0 else 0
                rank_class = 'gold' if i == 0 else (
                    'silver' if i == 1 else ('bronze' if i == 2 else ''))

                treatments.append({
                    'rank': i + 1,
                    'name': t['name'],
                    'count': t['procedure_count'],
                    'revenue': float(t['total_revenue']),
                    'avg_price': float(t['avg_price']),
                    'percent': percent,
                    'rank_class': rank_class
                })

        db.close()
        return jsonify({'success': True, 'treatments': treatments}), 200

    except Exception as e:
        print(f"Treatment popularity error: {e}")
        return jsonify({'error': 'Failed to fetch treatment data'}), 500

# =========================================
# Get Location and Referral Analytics
# =========================================


@analytics_bp.route('/location-referral', methods=['GET'])
@login_required
@role_required('superadmin')
def get_location_referral():
    """Get patient location and referral source analytics"""
    try:
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        location_data = []
        referral_data = []

        with db.cursor() as cursor:
            # Location distribution (based on address or city)
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN address LIKE '%Ikeja%' THEN 'Ikeja'
                        WHEN address LIKE '%Lagos%' OR address LIKE '%lagos%' THEN 'Lagos'
                        WHEN address LIKE '%Victoria Island%' OR address LIKE '%VI%' THEN 'Victoria Island'
                        ELSE 'Other Areas'
                    END as location,
                    COUNT(*) as count
                FROM patients
                WHERE address IS NOT NULL
                GROUP BY location
                ORDER BY count DESC
                LIMIT 5
            """)

            locations = cursor.fetchall()
            total = sum(l['count'] for l in locations)

            location_colors = ['#0066cc', '#34c759',
                               '#ff9500', '#9b59b6', '#ff6b6b']

            for i, loc in enumerate(locations):
                percent = (loc['count'] / total * 100) if total > 0 else 0
                location_data.append({
                    'name': loc['location'],
                    'count': loc['count'],
                    'percent': round(percent, 1),
                    'color': location_colors[i % len(location_colors)]
                })

            # Top area
            top_area = location_data[0]['name'] if location_data else 'Unknown'
            top_area_percent = location_data[0]['percent'] if location_data else 0

            # Referral sources (placeholder - you'd have a referral table)
            # For now, using sample distribution
            referral_data = [
                {'name': 'Word of Mouth', 'percent': 45, 'color': '#0066cc'},
                {'name': 'Previous Patients', 'percent': 30, 'color': '#34c759'},
                {'name': 'Social Media', 'percent': 15, 'color': '#ff9500'},
                {'name': 'Google Search', 'percent': 10, 'color': '#9b59b6'}
            ]

        db.close()

        return jsonify({
            'success': True,
            'location_data': location_data,
            'referral_data': referral_data,
            'top_area': top_area,
            'top_area_percent': top_area_percent
        }), 200

    except Exception as e:
        print(f"Location referral error: {e}")
        return jsonify({'error': 'Failed to fetch location data'}), 500

# =========================================
# Get Monthly Trends
# =========================================


@analytics_bp.route('/monthly-trends', methods=['GET'])
@login_required
@role_required('superadmin')
def get_monthly_trends():
    """Get monthly trends for patients and revenue"""
    try:
        year = request.args.get('year', datetime.now().year, type=int)
        db = get_db()
        if not db:
            return jsonify({'error': 'Database connection failed'}), 500

        monthly_data = []

        with db.cursor() as cursor:
            for month in range(1, 13):
                # Get patient count for month
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM patients
                    WHERE CAST(strftime('%Y', registration_date) AS INTEGER) = ? AND CAST(strftime('%m', registration_date) AS INTEGER) = ?
                """, (year, month))
                patients = cursor.fetchone()['count']

                # Get revenue for month
                cursor.execute("""
                    SELECT COALESCE(SUM(p.amount), 0) as total
                    FROM payments p
                    JOIN invoices i ON p.invoice_id = i.id
                    WHERE CAST(strftime('%Y', p.payment_date) AS INTEGER) = ? AND CAST(strftime('%m', p.payment_date) AS INTEGER) = ?
                """, (year, month))
                revenue = float(cursor.fetchone()[
                                'total']) / 100000  # Convert to ₦100K units

                monthly_data.append({
                    'month': datetime(year, month, 1).strftime('%b'),
                    'patients': patients,
                    'revenue': revenue
                })

        # Calculate growth
        if len(monthly_data) >= 2:
            first_patients = monthly_data[0]['patients']
            last_patients = monthly_data[-1]['patients']
            first_revenue = monthly_data[0]['revenue']
            last_revenue = monthly_data[-1]['revenue']

            patient_growth = round(
                ((last_patients - first_patients) / first_patients * 100), 1) if first_patients > 0 else 0
            revenue_growth = round(
                ((last_revenue - first_revenue) / first_revenue * 100), 1) if first_revenue > 0 else 0
        else:
            patient_growth = 0
            revenue_growth = 0

        db.close()

        return jsonify({
            'success': True,
            'monthly_data': monthly_data,
            'patient_growth': patient_growth,
            'revenue_growth': revenue_growth,
            'year': year
        }), 200

    except Exception as e:
        print(f"Monthly trends error: {e}")
        return jsonify({'error': 'Failed to fetch monthly trends'}), 500
