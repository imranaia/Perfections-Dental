// =========================================
// Perfections Dental Services
// Dynamic landing-page content — fetches /api/public/site-content and
// populates every [data-field]/[data-field-html] element, plus renders
// the team-members grid from the database. Runs for every visitor
// (not just edit mode); frontend/js/landing-editor.js builds on top of
// this for the superadmin "first person" editing experience.
// =========================================
(function () {
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function renderTeamCard(member) {
    const tags = (member.tags || '')
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const tagsHtml = tags
      .map((tag, i) => `<span class="tag${i === 1 ? ' green' : ''}">${escapeHtml(tag)}</span>`)
      .join('');

    const photo = member.photo_url || '';

    return `
      <div class="team-card reveal visible">
        <div class="team-img-wrap">
          ${photo ? `<img src="${escapeHtml(photo)}" alt="${escapeHtml(member.name)}" onerror="this.style.display='none'" />` : ''}
          <div class="team-ribbon">
            <div class="name">${escapeHtml(member.name)}</div>
            <div class="role">${escapeHtml(member.role_title)}</div>
          </div>
        </div>
        <div class="team-body">
          <p>${escapeHtml(member.bio || '')}</p>
          <div class="team-tags">${tagsHtml}</div>
        </div>
      </div>`;
  }

  async function loadSiteContent() {
    try {
      const res = await fetch('/api/public/site-content');
      const data = await res.json();
      if (!data.success) return data;

      const settings = data.settings || {};

      document.querySelectorAll('[data-field]').forEach((el) => {
        const key = el.getAttribute('data-field');
        if (settings[key]) el.textContent = settings[key];
      });

      document.querySelectorAll('[data-field-html]').forEach((el) => {
        const key = el.getAttribute('data-field-html');
        if (settings[key]) el.innerHTML = settings[key];
      });

      document.querySelectorAll('[data-field-src]').forEach((el) => {
        const key = el.getAttribute('data-field-src');
        if (settings[key]) el.src = settings[key];
      });

      const teamGrid = document.getElementById('teamGrid');
      if (teamGrid && Array.isArray(data.team) && data.team.length > 0) {
        teamGrid.innerHTML = data.team.map(renderTeamCard).join('');
      }

      return data;
    } catch (err) {
      console.error('Failed to load site content:', err);
      return null;
    }
  }

  window.PerfectionsSiteContent = { loadSiteContent, renderTeamCard };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadSiteContent);
  } else {
    loadSiteContent();
  }
})();
