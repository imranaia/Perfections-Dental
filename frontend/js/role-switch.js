// =========================================
// Perfections Dental Services
// Superadmin <-> Doctor role switch UI.
// Reuses the existing, already-working backend
// (POST /api/auth/switch-role) and frontend helpers
// (setActiveRole() in auth.js) -- this file only adds the missing UI:
//   - a "View as Doctor" control in the superadmin sidebar
//   - a "previewing as superadmin" banner on doctor pages, with a
//     button to switch back
// =========================================
(function () {
  async function getSession() {
    try {
      const res = await fetch('/api/auth/session', { credentials: 'include' });
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  function addSwitchToDoctorControl() {
    const sidebar = document.querySelector('.glass-sidebar');
    const brand = sidebar && sidebar.querySelector('.glass-brand');
    if (!sidebar || !brand || document.getElementById('roleSwitchLink')) return;

    const link = document.createElement('a');
    link.id = 'roleSwitchLink';
    link.href = '#';
    link.className = 'glass-nav-link';
    link.style.background = 'rgba(255,255,255,0.12)';
    link.style.marginBottom = '10px';
    link.innerHTML = '<i class="fas fa-user-doctor"></i> View as Doctor';
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      link.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Switching…';
      const result = await setActiveRole('doctor');
      if (result && result.redirect) {
        window.location.href = result.redirect;
      } else {
        link.innerHTML = '<i class="fas fa-user-doctor"></i> View as Doctor';
      }
    });
    brand.insertAdjacentElement('afterend', link);
  }

  function addPreviewBanner() {
    const main = document.querySelector('.glass-main');
    if (!main || document.getElementById('rolePreviewBanner')) return;

    const banner = document.createElement('div');
    banner.id = 'rolePreviewBanner';
    banner.style.cssText = `
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      background: var(--green-light); color: var(--green-dark); padding: 12px 18px;
      border-radius: var(--radius-sm); margin-bottom: 20px; font-size: 0.85rem; font-weight: 600;
      flex-wrap: wrap;
    `;
    banner.innerHTML = `
      <span><i class="fas fa-eye"></i> Previewing the Doctor experience as Superadmin — this shows the doctor UI, not a specific doctor's real data.</span>
      <button id="switchBackBtn" style="background:var(--green);color:#fff;border:none;border-radius:100px;padding:8px 16px;font-weight:700;cursor:pointer;font-size:0.82rem;">
        <i class="fas fa-arrow-left"></i> Switch back to Superadmin
      </button>
    `;
    main.insertBefore(banner, main.firstChild);

    document.getElementById('switchBackBtn').addEventListener('click', async () => {
      const result = await setActiveRole('superadmin');
      if (result && result.redirect) window.location.href = result.redirect;
    });
  }

  async function init() {
    const session = await getSession();
    if (!session || !session.authenticated) return;

    const trueRole = session.role;
    const activeRole = session.active_role;
    const canSwitch = session.user && session.user.can_switch_to_doctor;

    if (trueRole === 'superadmin' && activeRole === 'superadmin' && canSwitch) {
      addSwitchToDoctorControl();
    }

    if (trueRole === 'superadmin' && activeRole === 'doctor') {
      addPreviewBanner();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
