// =========================================
// Perfections Dental Services
// Authentication Module - v1.0
// Backend Connected
// =========================================

// API Configuration
const API_BASE_URL = window.location.origin + '/api';

// =========================================
// Toggle Password Visibility
// =========================================
function togglePassword() {
    const passwordInput = document.getElementById('password');
    const toggleBtn = document.querySelector('.toggle-password');
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
    } else {
        passwordInput.type = 'password';
        toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
    }
}

// =========================================
// Show/Hide Messages
// =========================================
function showMessage(type, message) {
    const errorMsg = document.getElementById('errorMessage');
    const successMsg = document.getElementById('successMessage');
    
    errorMsg.classList.remove('show');
    successMsg.classList.remove('show');
    
    if (type === 'error') {
        errorMsg.textContent = message;
        errorMsg.classList.add('show');
    } else if (type === 'success') {
        successMsg.textContent = message;
        successMsg.classList.add('show');
    }
    
    setTimeout(() => {
        errorMsg.classList.remove('show');
        successMsg.classList.remove('show');
    }, 5000);
}

// =========================================
// Show Loading Overlay
// =========================================
function showLoading(show = true) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        if (show) {
            overlay.classList.remove('hide');
        } else {
            overlay.classList.add('hide');
        }
    }
}

// =========================================
// Handle Login Form Submission
// =========================================
document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value.trim();
            
            if (!email || !password) {
                showMessage('error', 'Please enter both email and password');
                return;
            }
            
            showLoading(true);
            
            try {
                const response = await fetch(`${API_BASE_URL}/auth/login`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    credentials: 'include',
                    body: JSON.stringify({ email, password })
                });
                
                const data = await response.json();
                
                if (response.ok && data.success) {
                    sessionStorage.setItem('user', JSON.stringify(data.user));
                    sessionStorage.setItem('active_role', data.user.role);
                    
                    showMessage('success', 'Login successful! Redirecting...');
                    
                    setTimeout(() => {
                        window.location.href = data.redirect;
                    }, 1000);
                } else {
                    showLoading(false);
                    showMessage('error', data.error || 'Invalid email or password');
                }
            } catch (error) {
                console.error('Login error:', error);
                showLoading(false);
                showMessage('error', 'Network error. Please check if the server is running.');
            }
        });
    }
    
    const credentialItems = document.querySelectorAll('.credential-item');
    credentialItems.forEach(item => {
        item.addEventListener('click', () => {
            const email = item.getAttribute('data-email');
            const passwordInput = document.getElementById('password');
            const emailInput = document.getElementById('email');
            
            if (email) {
                emailInput.value = email;
                passwordInput.value = '1234';
                emailInput.focus();
            }
        });
    });
});

// =========================================
// Check if user is logged in (for protected pages)
// =========================================
async function checkAuth() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/session`, {
            method: 'GET',
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (!data.authenticated) {
            window.location.href = '/login.html';
            return null;
        }
        
        if (data.user) {
            const storedActiveRole = sessionStorage.getItem('active_role');
            
            sessionStorage.setItem('user', JSON.stringify(data.user));
            
            // Preserve active_role for superadmin
            if (data.user.role === 'superadmin' && storedActiveRole) {
                sessionStorage.setItem('active_role', storedActiveRole);
            } else {
                sessionStorage.setItem('active_role', data.active_role || data.user.role);
            }
        }
        
        return data.user;
    } catch (error) {
        console.error('Auth check error:', error);
        window.location.href = '/login.html';
        return null;
    }
}

// =========================================
// Get current user
// =========================================
function getCurrentUser() {
    const user = sessionStorage.getItem('user');
    return user ? JSON.parse(user) : null;
}

// =========================================
// Get active role (for superadmin switching)
// =========================================
function getActiveRole() {
    const activeRole = sessionStorage.getItem('active_role');
    if (activeRole) {
        return activeRole;
    }
    
    const user = getCurrentUser();
    if (user) {
        return user.role;
    }
    
    return null;
}

// =========================================
// Set active role (for superadmin switching)
// =========================================
async function setActiveRole(role) {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/switch-role`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ role })
        });
        
        const data = await response.json();
        
        if (data.success) {
            sessionStorage.setItem('active_role', role);
            return data;
        }
        return false;
    } catch (error) {
        console.error('Role switch error:', error);
        return false;
    }
}

// =========================================
// Logout function
// =========================================
async function logout() {
    try {
        await fetch(`${API_BASE_URL}/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    sessionStorage.clear();
    window.location.href = '/login.html';
}

// =========================================
// API Helper Functions
// =========================================
async function apiRequest(endpoint, options = {}) {
    const defaultOptions = {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        }
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, mergedOptions);
        const data = await response.json();
        
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/login.html';
                throw new Error('Session expired');
            }
            throw new Error(data.error || 'Request failed');
        }
        
        return data;
    } catch (error) {
        console.error('API request error:', error);
        throw error;
    }
}