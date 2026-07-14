// =========================================
// Perfections Dental Services
// Dashboard Module - v1.0
// Backend Connected
// =========================================

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', async () => {
    const user = await checkAuth();
    if (!user) return;
    
    loadUserProfile(user);
    loadSidebar(user);
    initSystemStatus();
    
    if (user.role === 'superadmin') {
        initRoleSwitch(user);
    }
    
    const currentPage = window.location.pathname.split('/').pop();
    if (currentPage === 'dashboard.html') {
        loadDashboardData();
    }
    
    loadPageContent();
});

// =========================================
// Load Dashboard Data from Backend
// =========================================
async function loadDashboardData() {
    try {
        const statsResponse = await fetch('/api/dashboard/stats', {
            credentials: 'include'
        });
        const statsData = await statsResponse.json();
        
        if (statsData.success) {
            updateDashboardStats(statsData.stats);
        }
        
        const activitiesResponse = await fetch('/api/dashboard/recent-activities', {
            credentials: 'include'
        });
        const activitiesData = await activitiesResponse.json();
        
        if (activitiesData.success) {
            updateRecentActivities(activitiesData.activities);
        }
        
        const chartResponse = await fetch('/api/dashboard/chart-data', {
            credentials: 'include'
        });
        const chartData = await chartResponse.json();
        
        if (chartData.success) {
            updateCharts(chartData);
        }
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showToast('error', 'Failed to load dashboard data');
    }
}

// =========================================
// Update Dashboard Stats
// =========================================
function updateDashboardStats(stats) {
    const statsContainer = document.querySelector('.stats-grid');
    if (!statsContainer) return;
    
    const activeRole = getActiveRole();
    
    if (activeRole === 'superadmin') {
        updateStatCard('total-staff', stats.total_staff || 0);
        updateStatCard('total-patients', stats.total_patients || 0);
        updateStatCard('today-appointments', stats.today_appointments || 0);
        updateStatCard('monthly-revenue', formatCurrency(stats.monthly_revenue || 0));
        updateStatCard('low-stock-alerts', stats.low_stock_alerts || 0);
        
        updateChangeIndicator('staff-change', stats.staff_change);
        updateChangeIndicator('appointments-change', stats.appointments_change);
        updateChangeIndicator('revenue-change', stats.revenue_change);
        
    } else if (activeRole === 'doctor') {
        updateStatCard('today-appointments', stats.today_appointments || 0);
        updateStatCard('total-patients', stats.total_patients || 0);
        updateStatCard('waiting-patients', stats.waiting_patients || 0);
        
    } else if (activeRole === 'nurse') {
        updateStatCard('today-assists', stats.today_assists || 0);
        updateStatCard('pending-tasks', stats.pending_tasks || 0);
        
    } else if (activeRole === 'reception') {
        updateStatCard('today-appointments', stats.today_appointments || 0);
        updateStatCard('new-patients', stats.new_patients || 0);
        updateStatCard('today-collections', formatCurrency(stats.today_collections || 0));
    }
}

// =========================================
// Helper: Update Stat Card
// =========================================
function updateStatCard(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

// =========================================
// Helper: Update Change Indicator
// =========================================
function updateChangeIndicator(id, changeValue) {
    const element = document.getElementById(id);
    if (element && changeValue !== undefined) {
        const isPositive = changeValue >= 0;
        element.innerHTML = `
            <i class="fas fa-arrow-${isPositive ? 'up' : 'down'}"></i>
            <span class="${isPositive ? 'text-success' : 'text-danger'}">${Math.abs(changeValue)}%</span>
            <span class="text-muted">vs last period</span>
        `;
    }
}

// =========================================
// Update Recent Activities
// =========================================
function updateRecentActivities(activities) {
    const activitiesContainer = document.querySelector('.activities-list');
    if (!activitiesContainer || !activities.length) return;
    
    let html = '';
    activities.forEach(activity => {
        const timeAgo = getTimeAgo(activity.created_at);
        html += `
            <div class="activity-item">
                <div class="activity-icon ${activity.badge_type || 'info'}">
                    <i class="${activity.icon || 'fas fa-bell'}"></i>
                </div>
                <div class="activity-content">
                    <div class="activity-title">${escapeHtml(activity.title)}</div>
                    <div class="activity-time">${timeAgo}</div>
                </div>
                ${activity.badge_text ? `<span class="activity-badge ${activity.badge_type}">${activity.badge_text}</span>` : ''}
            </div>
        `;
    });
    
    activitiesContainer.innerHTML = html;
}

// =========================================
// Update Charts
// =========================================
function updateCharts(chartData) {
    if (chartData.revenue_data && typeof Chart !== 'undefined') {
        const revenueCtx = document.getElementById('revenueChart');
        if (revenueCtx) {
            new Chart(revenueCtx, {
                type: 'line',
                data: {
                    labels: chartData.revenue_data.labels,
                    datasets: [{
                        label: 'Revenue (₦)',
                        data: chartData.revenue_data.values,
                        borderColor: '#0066cc',
                        backgroundColor: 'rgba(0, 102, 204, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top' }
                    }
                }
            });
        }
    }
    
    if (chartData.appointment_data && typeof Chart !== 'undefined') {
        const appointmentCtx = document.getElementById('appointmentChart');
        if (appointmentCtx) {
            new Chart(appointmentCtx, {
                type: 'doughnut',
                data: {
                    labels: chartData.appointment_data.labels,
                    datasets: [{
                        data: chartData.appointment_data.values,
                        backgroundColor: ['#34c759', '#ff9500', '#ff3b30', '#5856d6', '#ffcc00']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    }
                }
            });
        }
    }
}

// =========================================
// Load User Profile in Header
// =========================================
function loadUserProfile(user) {
    const profileElement = document.querySelector('.user-profile');
    if (!profileElement) return;
    
    let displayRole = '';
    
    if (user.role === 'superadmin') {
        const activeRole = getActiveRole();
        if (activeRole === 'doctor') {
            displayRole = 'Doctor (Viewing as Doctor)';
        } else {
            displayRole = 'Super Administrator';
        }
    } else {
        displayRole = user.role === 'doctor' ? 'Doctor' : 
                     user.role === 'nurse' ? 'Nurse' : 
                     user.role === 'reception' ? 'Receptionist' : user.role;
    }
    
    profileElement.innerHTML = `
        <div class="user-avatar">${user.avatar || (user.first_name?.[0] + user.last_name?.[0]) || 'U'}</div>
        <div class="user-info">
            <div class="user-name">${escapeHtml(user.name)}</div>
            <div class="user-role">${displayRole}</div>
        </div>
        <i class="fas fa-chevron-down" style="font-size: 0.8rem; color: var(--text-light);"></i>
    `;
    
    profileElement.addEventListener('click', () => {
        showProfileDropdown(profileElement);
    });
}

// =========================================
// Show Profile Dropdown
// =========================================
function showProfileDropdown(target) {
    const existingDropdown = document.querySelector('.profile-dropdown');
    if (existingDropdown) {
        existingDropdown.remove();
        return;
    }
    
    const dropdown = document.createElement('div');
    dropdown.className = 'profile-dropdown';
    dropdown.innerHTML = `
        <a href="#" onclick="logout(); return false;">
            <i class="fas fa-sign-out-alt"></i> Logout
        </a>
    `;
    
    target.appendChild(dropdown);
    
    setTimeout(() => {
        document.addEventListener('click', function closeDropdown(e) {
            if (!dropdown.contains(e.target) && !target.contains(e.target)) {
                dropdown.remove();
                document.removeEventListener('click', closeDropdown);
            }
        });
    }, 0);
}

// =========================================
// Load Sidebar Based on Role
// =========================================
function loadSidebar(user) {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    
    let activeRole = user.role;
    if (user.role === 'superadmin') {
        activeRole = getActiveRole() || user.role;
    }
    
    const menuContainer = sidebar.querySelector('.sidebar-menu');
    
    const menuItems = {
        superadmin: [
            { icon: 'fas fa-chart-line', text: 'Dashboard', link: 'dashboard.html' },
            { icon: 'fas fa-lock', text: 'Access control', link: 'access-control.html' },
            { icon: 'fas fa-coins', text: 'Financial', link: 'financial.html' },
            { icon: 'fas fa-chart-pie', text: 'Analytics', link: 'analytics.html' },
            { icon: 'fas fa-user-md', text: 'Doctors', link: 'doctors.html' },
            { icon: 'fas fa-user-nurse', text: 'Nurses', link: 'nurses.html' },
            { icon: 'fas fa-user-tie', text: 'Reception', link: 'reception.html' },
            { icon: 'fas fa-teeth-open', text: 'Services', link: 'services.html' },
            { icon: 'fas fa-pills', text: 'Inventory', link: 'inventory.html' },
            { icon: 'fas fa-chart-bar', text: 'Performance', link: 'performance.html' },
            { icon: 'fas fa-cog', text: 'Settings', link: 'settings.html' },
            { icon: 'fas fa-id-card', text: 'Profile', link: 'profile.html' }
        ],
        doctor: [
            { icon: 'fas fa-chart-line', text: 'Dashboard', link: 'dashboard.html' },
            { icon: 'fas fa-user-injured', text: 'My Patients', link: 'my-patients.html' },
            { icon: 'fas fa-calendar-alt', text: 'Schedule', link: 'schedule.html' },
            { icon: 'fas fa-notes-medical', text: 'Consult', link: 'consult.html' },
            { icon: 'fas fa-prescription', text: 'Prescribe', link: 'prescribe.html' },
            { icon: 'fas fa-x-ray', text: 'Records', link: 'records.html' },
            { icon: 'fas fa-id-card', text: 'Profile', link: 'profile.html' }
        ],
        nurse: [
            { icon: 'fas fa-chart-line', text: 'Dashboard', link: 'dashboard.html' },
            { icon: 'fas fa-hand-holding-medical', text: 'My Assists', link: 'my-assists.html' },
            { icon: 'fas fa-tooth', text: 'Procedures', link: 'procedures.html' },
            { icon: 'fas fa-pen', text: 'Notes', link: 'notes.html' },
            { icon: 'fas fa-prescription', text: 'Prescribe', link: 'prescribe.html' },
            { icon: 'fas fa-x-ray', text: 'Records', link: 'records.html' },
            { icon: 'fas fa-tasks', text: 'My Tasks', link: 'my-tasks.html' },
            { icon: 'fas fa-id-card', text: 'Profile', link: 'profile.html' }
        ],
        reception: [
            { icon: 'fas fa-chart-line', text: 'Dashboard', link: 'dashboard.html' },
            { icon: 'fas fa-calendar-check', text: 'Appointments', link: 'appointments.html' },
            { icon: 'fas fa-users', text: 'Patients', link: 'patients.html' },
            { icon: 'fas fa-teeth-open', text: 'Services', link: 'services.html' },
            { icon: 'fas fa-credit-card', text: 'Payments', link: 'payments.html' },
            { icon: 'fas fa-chart-bar', text: 'Reports', link: 'reports.html' },
            { icon: 'fas fa-pills', text: 'Inventory', link: 'inventory.html' },
            { icon: 'fas fa-file-invoice', text: 'Invoices', link: 'invoices.html' },
            { icon: 'fas fa-id-card', text: 'Profile', link: 'profile.html' }
        ]
    };
    
    const currentPage = window.location.pathname.split('/').pop();
    
    let menuHTML = '';
    const items = menuItems[activeRole] || menuItems[user.role];
    
    items.forEach(item => {
        const isActive = currentPage === item.link;
        menuHTML += `
            <div class="menu-item ${isActive ? 'active' : ''}" onclick="navigateTo('${item.link}')">
                <i class="${item.icon}"></i>
                <span>${item.text}</span>
            </div>
        `;
    });
    
    menuContainer.innerHTML = menuHTML;
}

// =========================================
// Navigation Helper
// =========================================
function navigateTo(page) {
    window.location.href = page;
}

// =========================================
// Initialize Role Switch for SuperAdmin
// =========================================
function initRoleSwitch(user) {
    const container = document.querySelector('.role-switch-container');
    if (!container) return;
    
    // Show role switch on BOTH superadmin AND doctor pages when user is superadmin
    const currentPath = window.location.pathname;
    const isSuperadminPage = currentPath.includes('/superadmin/');
    const isDoctorPage = currentPath.includes('/doctor/');
    
    // Only show if on superadmin page OR (on doctor page AND user is superadmin)
    if (!isSuperadminPage && !(isDoctorPage && user.role === 'superadmin')) {
        return;
    }
    
    const activeRole = getActiveRole() || user.role;
    
    container.innerHTML = `
        <div class="role-switch">
            <div class="role-option ${activeRole === 'superadmin' ? 'active' : ''}" onclick="switchRole('superadmin')">
                <i class="fas fa-crown"></i> Admin
            </div>
            <div class="role-option ${activeRole === 'doctor' ? 'active' : ''}" onclick="switchRole('doctor')">
                <i class="fas fa-user-md"></i> Doctor
            </div>
        </div>
    `;
}

// =========================================
// Switch Role (SuperAdmin only)
// =========================================
async function switchRole(role) {
    const user = getCurrentUser();
    if (!user || user.role !== 'superadmin') return;
    
    try {
        const result = await setActiveRole(role);
        
        if (result && result.success) {
            sessionStorage.setItem('active_role', role);
            
            const currentUser = getCurrentUser();
            if (currentUser) {
                currentUser.active_role = role;
                sessionStorage.setItem('user', JSON.stringify(currentUser));
            }
            
            showToast('success', `Switched to ${role === 'superadmin' ? 'Admin' : 'Doctor'} view`);
            
            // Redirect to the appropriate dashboard
            if (role === 'doctor') {
                window.location.href = '/pages/doctor/dashboard.html';
            } else {
                window.location.href = '/pages/superadmin/dashboard.html';
            }
        } else {
            showToast('error', result?.error || 'Failed to switch role');
        }
    } catch (error) {
        console.error('Role switch error:', error);
        showToast('error', 'Failed to switch role');
    }
}

// =========================================
// Initialize System Status
// =========================================
function initSystemStatus() {
    const statusElement = document.querySelector('.system-status');
    if (!statusElement) return;
    
    const isOnline = navigator.onLine;
    
    statusElement.innerHTML = `
        <span class="status-dot" style="background: ${isOnline ? '#34c759' : '#ff3b30'};"></span>
        <span class="status-text ${isOnline ? '' : 'offline'}">
            ${isOnline ? 'Online' : 'Offline Mode'}
        </span>
    `;
    
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
}

// =========================================
// Update Online Status
// =========================================
function updateOnlineStatus() {
    const statusElement = document.querySelector('.system-status');
    if (!statusElement) return;
    
    const isOnline = navigator.onLine;
    
    statusElement.innerHTML = `
        <span class="status-dot" style="background: ${isOnline ? '#34c759' : '#ff3b30'};"></span>
        <span class="status-text ${isOnline ? '' : 'offline'}">
            ${isOnline ? 'Online' : 'Offline Mode'}
        </span>
    `;
}

// =========================================
// Toggle Sidebar on Mobile
// =========================================
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('show');
    }
}

// =========================================
// Load Page Specific Content
// =========================================
function loadPageContent() {
    const currentPage = window.location.pathname.split('/').pop();
    
    const pageTitle = document.querySelector('.page-title');
    if (pageTitle) {
        const titles = {
            'dashboard.html': 'Dashboard',
            'access-control.html': 'Access Control',
            'financial.html': 'Financial Overview',
            'analytics.html': 'Analytics',
            'doctors.html': 'Doctors Management',
            'nurses.html': 'Nurses Management',
            'reception.html': 'Reception Staff',
            'inventory.html': 'Inventory Management',
            'performance.html': 'Staff Performance',
            'settings.html': 'System Settings',
            'my-patients.html': 'My Patients',
            'schedule.html': 'Schedule',
            'consult.html': 'Consultation',
            'prescribe.html': 'Prescribe Medication',
            'records.html': 'Patient Records',
            'my-assists.html': 'My Assists',
            'procedures.html': 'Procedures',
            'notes.html': 'Clinical Notes',
            'my-tasks.html': 'My Tasks',
            'appointments.html': 'Appointments',
            'patients.html': 'Patients Management',
            'payments.html': 'Payments',
            'reports.html': 'Reports',
            'invoices.html': 'Invoices',
            'services.html': 'Services',
            'profile.html': 'My Profile'
        };
        
        pageTitle.textContent = titles[currentPage] || 'Perfections Dental';
    }
}

// =========================================
// Helper: Show Toast Message
// =========================================
function showToast(type, message) {
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// =========================================
// Helper: Format Currency
// =========================================
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-NG', {
        style: 'currency',
        currency: 'NGN',
        minimumFractionDigits: 0
    }).format(amount);
}

// =========================================
// Helper: Get Time Ago
// =========================================
function getTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} day${days > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
}

// =========================================
// Helper: Escape HTML
// =========================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}