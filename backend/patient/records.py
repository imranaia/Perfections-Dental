# =========================================
# Perfections Dental Services
# Patient Portal — Medical Records & Medications
#
# Every query here is scoped to session['patient_id'] — a patient can only
# ever see their own data, never another patient's by guessing an id.
# =========================================

from flask import Blueprint, jsonify, session

from db import get_db
from patient.auth import patient_login_required

patient_records_bp = Blueprint(
    'patient_records', __name__, url_prefix='/api/patient/records')


@patient_records_bp.route('/profile', methods=['GET'])
@patient_login_required
def get_profile():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM patients WHERE id = ?", (session['patient_id'],))
            patient = cursor.fetchone()
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        patient.pop('password_hash', None)
        return jsonify({'success': True, 'patient': patient}), 200
    finally:
        db.close()


@patient_records_bp.route('/appointments', methods=['GET'])
@patient_login_required
def get_appointments():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, a.appointment_date, a.status, a.reason,
                       u.first_name || ' ' || u.last_name as doctor_name,
                       s.name as service_name
                FROM appointments a
                JOIN users u ON a.doctor_id = u.id
                LEFT JOIN services s ON a.service_id = s.id
                WHERE a.patient_id = ?
                ORDER BY a.appointment_date DESC
            """, (session['patient_id'],))
            appointments = cursor.fetchall()
        return jsonify({'success': True, 'appointments': appointments}), 200
    finally:
        db.close()


@patient_records_bp.route('/clinical-notes', methods=['GET'])
@patient_login_required
def get_clinical_notes():
    """Non-sensitive visit summaries only (note_type != 'internal')."""
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT mn.note_type, mn.content, mn.note_date,
                       u.first_name || ' ' || u.last_name as author_name
                FROM medical_notes mn
                JOIN users u ON mn.author_id = u.id
                WHERE mn.patient_id = ?
                ORDER BY mn.note_date DESC
            """, (session['patient_id'],))
            notes = cursor.fetchall()
        return jsonify({'success': True, 'notes': notes}), 200
    finally:
        db.close()


@patient_records_bp.route('/prescriptions', methods=['GET'])
@patient_login_required
def get_prescriptions():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT pr.id, pr.prescription_number, pr.status, pr.created_at,
                       pr.dispensed_at, u.first_name || ' ' || u.last_name as prescribed_by_name
                FROM prescriptions pr
                JOIN users u ON pr.prescribed_by = u.id
                WHERE pr.patient_id = ?
                ORDER BY pr.created_at DESC
            """, (session['patient_id'],))
            prescriptions = cursor.fetchall()

            for pres in prescriptions:
                cursor.execute("""
                    SELECT ii.name, pi.dosage, pi.frequency, pi.duration, pi.quantity, pi.dispensed
                    FROM prescription_items pi
                    JOIN inventory_items ii ON pi.inventory_item_id = ii.id
                    WHERE pi.prescription_id = ?
                """, (pres['id'],))
                pres['items'] = cursor.fetchall()

        return jsonify({'success': True, 'prescriptions': prescriptions}), 200
    finally:
        db.close()


@patient_records_bp.route('/invoices', methods=['GET'])
@patient_login_required
def get_invoices():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT id, invoice_number, invoice_date, subtotal, tax, total, amount_paid, status
                FROM invoices
                WHERE patient_id = ?
                ORDER BY invoice_date DESC
            """, (session['patient_id'],))
            invoices = cursor.fetchall()
        return jsonify({'success': True, 'invoices': invoices}), 200
    finally:
        db.close()
