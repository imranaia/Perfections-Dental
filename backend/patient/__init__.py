# =========================================
# Perfections Dental Services — Patient Portal
# =========================================
from .auth import patient_bp
from .records import patient_records_bp
from .appointments import patient_appointments_bp

__all__ = ['patient_bp', 'patient_records_bp', 'patient_appointments_bp']
