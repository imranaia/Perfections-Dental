# backend/superadmin/__init__.py
# =========================================
# Perfections Dental Services
# SuperAdmin Package Initialization
# =========================================

from .dashboard import superadmin_bp
from .access_control import access_control_bp
from .financial import financial_bp
from .analytics import analytics_bp
from .doctors import doctors_bp
from .nurses import nurses_bp
from .reception import reception_bp
from .services import services_bp
from .inventory import inventory_bp
from .performance import performance_bp
from .settings import settings_bp
from .profile import profile_bp

__all__ = ['superadmin_bp', 'access_control_bp',
           'financial_bp', 'analytics_bp', 'doctors_bp',
           'nurses_bp', 'reception_bp', 'services_bp',
           'inventory_bp', 'performance_bp', 'settings_bp',
           'profile_bp']
