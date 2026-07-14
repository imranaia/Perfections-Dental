# =========================================
# Perfections Dental Services
# Reception Package Initialization
# =========================================

from .dashboard import reception_staff_bp
from .appointments import appointments_bp
from .patients import patients_bp
from .services import reception_services_bp
from .payments import payments_bp
from .reports import reports_bp
from .inventory import reception_inventory_bp
from .invoices import reception_invoices_bp
from .profile import reception_profile_bp

__all__ = [
    'reception_staff_bp',
    'appointments_bp',
    'patients_bp',
    'reception_services_bp',
    'payments_bp',
    'reception_services_bp',
    'reports_bp',
    'reception_inventory_bp'
    'reception_invoices_bp'
    'reception_profile_bp'
]
