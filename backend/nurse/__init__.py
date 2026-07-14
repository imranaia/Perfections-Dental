# =========================================
# Perfections Dental Services
# Nurse Package Initialization
# =========================================

from .dashboard import nurse_bp
from .my_assists import my_assists_bp
from .my_tasks import my_tasks_bp
from .notes import notes_bp
from .prescribe import nurse_prescribe_bp
from .procedures import procedures_bp
from .profile import nurse_profile_bp
from .records import nurse_records_bp

# Export blueprints
__all__ = [
    'nurse_bp',
    'my_assists_bp',
    'my_tasks_bp',
    'notes_bp',
    'nurse_prescribe_bp',
    'procedures_bp',
    'nurse_profile_bp',
    'nurse_records_bp'
]
