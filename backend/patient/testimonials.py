# =========================================
# Perfections Dental Services
# Patient Portal — Submit a Rating/Review
#
# Publishes immediately (product decision, confirmed with the clinic) --
# no admin approval step. Feeds the landing page's "What Our Patients
# Say" section via GET /api/public/site-content. Superadmin can still
# edit or remove a submission afterwards from the landing-page editor
# (backend/superadmin/testimonials.py), but nothing gates it pre-publish.
# =========================================

from flask import Blueprint, jsonify, session, request

from db import get_db
from patient.auth import patient_login_required

patient_testimonials_bp = Blueprint(
    'patient_testimonials', __name__, url_prefix='/api/patient/testimonials')


@patient_testimonials_bp.route('/', methods=['POST'])
@patient_login_required
def create_testimonial():
    try:
        data = request.get_json() or {}
        quote = (data.get('quote') or '').strip()
        rating = data.get('rating')

        if not quote:
            return jsonify({'error': 'Please write a review before submitting'}), 400
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({'error': 'Rating must be a number from 1 to 5'}), 400
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400

        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "SELECT first_name, last_name FROM patients WHERE id = ?",
                    (session['patient_id'],))
                patient = cursor.fetchone()
                if not patient:
                    return jsonify({'error': 'Patient not found'}), 404

                last_initial = f"{patient['last_name'][0]}." if patient['last_name'] else ''
                author_name = f"{patient['first_name']} {last_initial}".strip()

                cursor.execute("""
                    INSERT INTO testimonials
                        (patient_id, author_name, author_role, quote, rating, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (session['patient_id'], author_name, 'Verified Patient', quote, rating))
                db.commit()

            return jsonify({'success': True, 'message': 'Thank you for your review!'}), 201
        finally:
            db.close()
    except Exception as e:
        print(f"Create testimonial error: {e}")
        return jsonify({'error': 'Failed to submit review'}), 500


@patient_testimonials_bp.route('/mine', methods=['GET'])
@patient_login_required
def get_my_testimonials():
    """So the patient's own dashboard can show what they've already submitted."""
    try:
        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT id, quote, rating, created_at FROM testimonials
                    WHERE patient_id = ? ORDER BY created_at DESC
                """, (session['patient_id'],))
                reviews = [dict(row) for row in cursor.fetchall()]
            return jsonify({'success': True, 'reviews': reviews}), 200
        finally:
            db.close()
    except Exception as e:
        print(f"Get my testimonials error: {e}")
        return jsonify({'error': 'Failed to fetch reviews'}), 500
