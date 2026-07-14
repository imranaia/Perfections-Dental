# =========================================
# Perfections Dental Services
# Doctor Package Initialization
# =========================================

from .dashboard import doctor_bp
from .consult import consult_bp
from .my_patients import my_patients_bp
from .prescribe import prescribe_bp
from .profile import doctor_profile_bp
from .records import records_bp
from .schedule import schedule_bp

# Export blueprints
__all__ = [
    'doctor_bp',
    'consult_bp',
    'my_patients_bp',
    'prescribe_bp',
    'doctor_profile_bp',
    'records_bp',
    'schedule_bp'
]
