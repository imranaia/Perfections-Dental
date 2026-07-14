// =========================================
// Perfections Dental Services
// Collapsible sidebar — shared by every glass.css dashboard page
// =========================================
(function () {
  function initSidebar() {
    const sidebar = document.querySelector('.glass-sidebar');
    if (!sidebar) return;

    let backdrop = document.querySelector('.glass-sidebar-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.className = 'glass-sidebar-backdrop';
      document.body.appendChild(backdrop);
    }

    let toggle = sidebar.querySelector('.glass-sidebar-toggle');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.className = 'glass-sidebar-toggle';
      toggle.type = 'button';
      toggle.setAttribute('aria-label', 'Toggle menu');
      toggle.innerHTML = '<i class="fas fa-bars"></i>';
      // Docked right after the brand/logo block, not before it — the logo
      // should always be the first thing visible at the top of the rail.
      const brand = sidebar.querySelector('.glass-brand');
      if (brand && brand.nextSibling) {
        sidebar.insertBefore(toggle, brand.nextSibling);
      } else if (brand) {
        sidebar.appendChild(toggle);
      } else {
        sidebar.insertBefore(toggle, sidebar.firstChild);
      }
    }

    function setOpen(open) {
      sidebar.classList.toggle('open', open);
      backdrop.classList.toggle('show', open);
      toggle.innerHTML = open ? '<i class="fas fa-xmark"></i>' : '<i class="fas fa-bars"></i>';
    }

    toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('open')));
    backdrop.addEventListener('click', () => setOpen(false));

    // Close after picking a destination — works for real hrefs and the
    // patient dashboard's data-tab single-page nav alike.
    sidebar.querySelectorAll('.glass-nav-link').forEach((link) => {
      link.addEventListener('click', () => setOpen(false));
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebar);
  } else {
    initSidebar();
  }
})();
