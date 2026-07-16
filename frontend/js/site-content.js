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
      <div class="team-card reveal visible" data-team-id="${member.id}">
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

  function renderGalleryItem(image) {
    return `
      <div class="gallery-item" data-gallery-id="${image.id}">
        <img src="${escapeHtml(image.image_url)}" alt="${escapeHtml(image.caption || '')}" onerror="this.style.display='none'" />
        <div class="gallery-overlay"><span>${escapeHtml(image.caption || '')}</span></div>
      </div>`;
  }

  function initials(name) {
    return (name || '')
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join('');
  }

  function renderTestiCard(t) {
    const rating = Math.max(1, Math.min(5, parseInt(t.rating, 10) || 5));
    const stars = '★'.repeat(rating) + '☆'.repeat(5 - rating);
    return `
      <div class="testi-card reveal visible" data-testi-id="${t.id}">
        <div class="testi-quote">"</div>
        <div class="stars">${stars}</div>
        <p class="testi-text">${escapeHtml(t.quote)}</p>
        <div class="testi-author">
          <div class="testi-av">${escapeHtml(initials(t.author_name))}</div>
          <div class="testi-name">
            <strong>${escapeHtml(t.author_name)}</strong>
            <span>${escapeHtml(t.author_role || '')}</span>
          </div>
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

      document.querySelectorAll('[data-field-href]').forEach((el) => {
        const key = el.getAttribute('data-field-href');
        if (settings[key]) el.href = settings[key];
      });

      const teamGrid = document.getElementById('teamGrid');
      if (teamGrid && Array.isArray(data.team) && data.team.length > 0) {
        teamGrid.innerHTML = data.team.map(renderTeamCard).join('');
      }

      const galleryGrid = document.getElementById('galleryGrid');
      if (galleryGrid && Array.isArray(data.gallery) && data.gallery.length > 0) {
        galleryGrid.innerHTML = data.gallery.map(renderGalleryItem).join('');
      }

      const testiGrid = document.getElementById('testiGrid');
      if (testiGrid && Array.isArray(data.testimonials) && data.testimonials.length > 0) {
        testiGrid.innerHTML = data.testimonials.map(renderTestiCard).join('');
      }

      return data;
    } catch (err) {
      console.error('Failed to load site content:', err);
      return null;
    }
  }

  window.PerfectionsSiteContent = { loadSiteContent, renderTeamCard, renderGalleryItem, renderTestiCard };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadSiteContent);
  } else {
    loadSiteContent();
  }
})();
