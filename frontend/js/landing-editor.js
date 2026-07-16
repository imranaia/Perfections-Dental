// =========================================
// Perfections Dental Services
// "First person" landing-page editor — lets a superadmin edit the real
// rendered landing page in place (text, photos, team members) instead of
// a separate mockup/admin form. Only activates with ?edit=1 in the URL
// AND a confirmed superadmin session; otherwise this script is a no-op
// and the page renders exactly as it does for a normal visitor.
//
// Real write security is still the existing @role_required('superadmin')
// on every backend endpoint this calls — this script only controls
// whether the edit UI is shown.
// =========================================
(function () {
  if (new URLSearchParams(location.search).get('edit') !== '1') return;

  const STYLE = `
    .pd-editable { outline: 1px dashed rgba(4,80,160,0.4); outline-offset: 3px; cursor: text; border-radius: 4px; }
    .pd-editable:focus { outline: 2px solid var(--blue); background: rgba(234,244,255,0.6); }
    .pd-editable-link { outline: 2px dashed rgba(29,181,104,0.55); outline-offset: 2px; cursor: pointer !important; }
    .pd-photo-overlay {
      position: absolute; inset: 0; background: rgba(2,20,45,0.55); color: #fff;
      display: flex; align-items: center; justify-content: center; opacity: 0;
      transition: opacity 0.2s; cursor: pointer; font-size: 1.4rem; z-index: 5;
    }
    .pd-photo-overlay:hover { opacity: 1; }
    .team-img-wrap, #logoMark, .hero-card, .gallery-item { position: relative; }
    /* .pd-photo-overlay sits at z-index:5 to cover the whole image; these
       are already position:absolute in the base stylesheet (pinned to the
       bottom of the image) but need an explicit z-index above 5 too, or
       the overlay (invisible until hover, but still hit-testable) silently
       swallows clicks meant for the editable text inside them. */
    .team-ribbon, .gallery-overlay { z-index: 6; }
    .pd-team-delete {
      position: absolute; top: 8px; right: 8px; z-index: 6; width: 28px; height: 28px;
      border-radius: 50%; border: none; background: rgba(192,57,43,0.9); color: #fff;
      cursor: pointer; font-size: 0.9rem; display: flex; align-items: center; justify-content: center;
    }
    .pd-add-team, .pd-add-photo {
      border: 2px dashed rgba(4,80,160,0.35); border-radius: 28px; display: flex;
      align-items: center; justify-content: center; min-height: 220px; cursor: pointer;
      color: var(--blue); font-weight: 700; background: rgba(234,244,255,0.4);
    }
    .pd-edit-bar {
      position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 1000;
      background: var(--blue-dark); color: #fff; padding: 14px 22px; border-radius: 100px;
      display: flex; align-items: center; gap: 14px; box-shadow: 0 20px 44px rgba(2,20,45,0.4);
      font-family: var(--font-body); font-size: 0.9rem;
    }
    .pd-edit-bar button {
      border: none; border-radius: 100px; padding: 9px 18px; font-weight: 700; cursor: pointer;
      font-size: 0.85rem;
    }
    .pd-save-btn { background: var(--green); color: #fff; }
    .pd-exit-btn { background: rgba(255,255,255,0.15); color: #fff; }
    .pd-status { font-size: 0.8rem; color: rgba(255,255,255,0.7); }
  `;

  function injectStyle() {
    const tag = document.createElement('style');
    tag.textContent = STYLE;
    document.head.appendChild(tag);
  }

  async function api(path, options) {
    const res = await fetch(path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request to ${path} failed`);
    return data;
  }

  async function uploadPhoto(file) {
    const form = new FormData();
    form.append('photo', file);
    const res = await fetch('/api/superadmin/uploads', {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload failed');
    return data.url;
  }

  function addPhotoOverlay(container, imgEl, onUploaded) {
    const overlay = document.createElement('div');
    overlay.className = 'pd-photo-overlay';
    overlay.innerHTML = '<i class="fas fa-camera"></i>';
    overlay.addEventListener('click', () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/png,image/jpeg,image/webp';
      input.addEventListener('change', async () => {
        const file = input.files[0];
        if (!file) return;
        overlay.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        try {
          const url = await uploadPhoto(file);
          imgEl.src = url;
          imgEl.style.display = '';
          onUploaded(url);
        } catch (err) {
          alert(err.message);
        }
        overlay.innerHTML = '<i class="fas fa-camera"></i>';
      });
      input.click();
    });
    container.appendChild(overlay);
  }

  function makeTeamCardEditable(card, id) {
    card.dataset.teamId = id != null ? String(id) : '';

    const nameEl = card.querySelector('.team-ribbon .name');
    const roleEl = card.querySelector('.team-ribbon .role');
    const bioEl = card.querySelector('.team-body p');
    const tagsWrap = card.querySelector('.team-tags');
    [nameEl, roleEl, bioEl].forEach((el) => {
      if (el) { el.contentEditable = 'true'; el.classList.add('pd-editable'); }
    });
    if (tagsWrap) {
      tagsWrap.contentEditable = 'true';
      tagsWrap.classList.add('pd-editable');
      tagsWrap.title = 'Comma-separated tags — plain text is fine here';
    }

    const delBtn = document.createElement('button');
    delBtn.className = 'pd-team-delete';
    delBtn.innerHTML = '<i class="fas fa-xmark"></i>';
    delBtn.title = 'Remove team member';
    delBtn.addEventListener('click', async () => {
      if (!confirm('Remove this team member?')) return;
      if (card.dataset.teamId) {
        try { await api(`/api/superadmin/team/${card.dataset.teamId}`, { method: 'DELETE' }); }
        catch (err) { alert(err.message); return; }
      }
      card.remove();
    });
    card.style.position = 'relative';
    card.appendChild(delBtn);

    const imgWrap = card.querySelector('.team-img-wrap');
    const img = card.querySelector('.team-img-wrap img');
    if (imgWrap && img) {
      addPhotoOverlay(imgWrap, img, (url) => { card.dataset.photoUrl = url; });
    }
  }

  function addTeamMemberButton(grid) {
    const btn = document.createElement('div');
    // Deliberately NOT class "team-card" -- both setupTeamEditing() and
    // saveAll() query ".team-card" to find real member cards, and this
    // placeholder must never be picked up as one (it has no name/role/bio
    // fields for saveAll to read).
    btn.className = 'pd-add-team';
    btn.innerHTML = '<div><i class="fas fa-plus"></i><br>Add team member</div>';
    btn.addEventListener('click', () => {
      const card = document.createElement('div');
      card.className = 'team-card';
      card.innerHTML = `
        <div class="team-img-wrap">
          <div class="team-placeholder"><i class="fas fa-user-doctor"></i></div>
          <div class="team-ribbon">
            <div class="name">New team member</div>
            <div class="role">Role / title</div>
          </div>
        </div>
        <div class="team-body">
          <p>Short bio…</p>
          <div class="team-tags"><span class="tag">Tag</span></div>
        </div>`;
      grid.insertBefore(card, btn);
      makeTeamCardEditable(card, null);
    });
    grid.appendChild(btn);
  }

  function setupTeamEditing() {
    const grid = document.getElementById('teamGrid');
    if (!grid) return;
    grid.querySelectorAll('.team-card').forEach((card, i) => {
      // Cards rendered by site-content.js carry no id marker of their own,
      // so treat every existing card as "new" (id null) unless it was
      // already tagged — the first save turns hardcoded/fallback cards
      // into real rows.
      makeTeamCardEditable(card, card.dataset.teamId || null);
    });
    addTeamMemberButton(grid);
  }

  function makeGalleryItemEditable(item, id) {
    item.dataset.galleryId = id != null ? String(id) : '';

    let overlay = item.querySelector('.gallery-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'gallery-overlay';
      overlay.innerHTML = '<span></span>';
      item.appendChild(overlay);
    }
    overlay.style.opacity = '1'; // the caption is hover-only normally; force visible while editing
    const captionEl = overlay.querySelector('span');
    captionEl.contentEditable = 'true';
    captionEl.classList.add('pd-editable');

    const delBtn = document.createElement('button');
    delBtn.className = 'pd-team-delete';
    delBtn.innerHTML = '<i class="fas fa-xmark"></i>';
    delBtn.title = 'Remove photo';
    delBtn.addEventListener('click', async () => {
      if (!confirm('Remove this photo?')) return;
      if (item.dataset.galleryId) {
        try { await api(`/api/superadmin/gallery/${item.dataset.galleryId}`, { method: 'DELETE' }); }
        catch (err) { alert(err.message); return; }
      }
      item.remove();
    });
    item.appendChild(delBtn);

    const img = item.querySelector('img');
    if (img) {
      addPhotoOverlay(item, img, (url) => { item.dataset.photoUrl = url; });
    }
  }

  function addGalleryPhotoButton(grid) {
    const btn = document.createElement('div');
    // Deliberately NOT class "gallery-item" -- see the equivalent note on
    // addTeamMemberButton()'s "team-card" exclusion.
    btn.className = 'pd-add-photo';
    btn.innerHTML = '<div><i class="fas fa-plus"></i><br>Add photo</div>';
    btn.addEventListener('click', () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/png,image/jpeg,image/webp';
      input.addEventListener('change', async () => {
        const file = input.files[0];
        if (!file) return;
        try {
          const url = await uploadPhoto(file);
          const item = document.createElement('div');
          item.className = 'gallery-item';
          item.innerHTML = `<img src="${url}" alt="" /><div class="gallery-overlay"><span>New photo</span></div>`;
          grid.insertBefore(item, btn);
          makeGalleryItemEditable(item, null);
        } catch (err) {
          alert(err.message);
        }
      });
      input.click();
    });
    grid.appendChild(btn);
  }

  function setupGalleryEditing() {
    const grid = document.getElementById('galleryGrid');
    if (!grid) return;
    grid.querySelectorAll('.gallery-item').forEach((item) => {
      makeGalleryItemEditable(item, item.dataset.galleryId || null);
    });
    addGalleryPhotoButton(grid);
  }

  function makeTestiCardEditable(card, id) {
    card.dataset.testiId = id != null ? String(id) : '';

    const quoteEl = card.querySelector('.testi-text');
    const nameEl = card.querySelector('.testi-name strong');
    const roleEl = card.querySelector('.testi-name span');
    [quoteEl, nameEl, roleEl].forEach((el) => {
      if (el) { el.contentEditable = 'true'; el.classList.add('pd-editable'); }
    });

    const delBtn = document.createElement('button');
    delBtn.className = 'pd-team-delete';
    delBtn.innerHTML = '<i class="fas fa-xmark"></i>';
    delBtn.title = 'Remove review';
    delBtn.addEventListener('click', async () => {
      if (!confirm('Remove this review?')) return;
      if (card.dataset.testiId) {
        try { await api(`/api/superadmin/testimonials/${card.dataset.testiId}`, { method: 'DELETE' }); }
        catch (err) { alert(err.message); return; }
      }
      card.remove();
    });
    card.style.position = 'relative';
    card.appendChild(delBtn);
  }

  function setupTestimonialEditing() {
    // No "add" button here on purpose -- reviews come from patients
    // (backend/patient/testimonials.py), superadmin can only edit/remove
    // what's already been submitted, same as any other moderation view.
    const grid = document.getElementById('testiGrid');
    if (!grid) return;
    grid.querySelectorAll('.testi-card').forEach((card) => {
      makeTestiCardEditable(card, card.dataset.testiId || null);
    });
  }

  function setupFieldEditing() {
    document.querySelectorAll('[data-field], [data-field-html]').forEach((el) => {
      el.contentEditable = 'true';
      el.classList.add('pd-editable');
    });
    const logoMark = document.getElementById('logoMark');
    const logoImg = logoMark && logoMark.querySelector('img');
    if (logoMark && logoImg) {
      addPhotoOverlay(logoMark, logoImg, () => {});
    }

    const heroCard = document.querySelector('.hero-card');
    const heroImg = heroCard && heroCard.querySelector('img[data-field-src]');
    if (heroCard && heroImg) {
      addPhotoOverlay(heroCard, heroImg, () => {});
    }

    // Links (e.g. the footer's social icons) can't be made contenteditable
    // the way text can -- clicking prompts for the URL instead of
    // navigating away while in edit mode.
    document.querySelectorAll('[data-field-href]').forEach((el) => {
      el.classList.add('pd-editable-link');
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const current = el.getAttribute('href') === '#' ? '' : el.getAttribute('href');
        const url = prompt('Link URL:', current || '');
        if (url !== null && url.trim()) {
          el.setAttribute('href', url.trim());
        }
      });
    });
  }

  async function saveAll(statusEl) {
    statusEl.textContent = 'Saving…';
    try {
      const settings = {};
      document.querySelectorAll('[data-field]').forEach((el) => {
        settings[el.getAttribute('data-field')] = el.textContent.trim();
      });
      document.querySelectorAll('[data-field-html]').forEach((el) => {
        settings[el.getAttribute('data-field-html')] = el.innerHTML.trim();
      });
      document.querySelectorAll('[data-field-src]').forEach((el) => {
        if (el.src) settings[el.getAttribute('data-field-src')] = el.getAttribute('src');
      });
      document.querySelectorAll('[data-field-href]').forEach((el) => {
        const href = el.getAttribute('href');
        if (href && href !== '#') settings[el.getAttribute('data-field-href')] = href;
      });
      await api('/api/superadmin/settings/', { method: 'POST', body: JSON.stringify(settings) });

      const grid = document.getElementById('teamGrid');
      const cards = grid ? Array.from(grid.querySelectorAll('.team-card')) : [];
      for (let i = 0; i < cards.length; i++) {
        const card = cards[i];
        const clean = (s) => s.replace(/\s+/g, ' ').trim();
        const name = clean(card.querySelector('.team-ribbon .name').textContent);
        const role_title = clean(card.querySelector('.team-ribbon .role').textContent);
        const bio = clean(card.querySelector('.team-body p').textContent);
        const tags = Array.from(card.querySelectorAll('.team-tags .tag')).map((t) => clean(t.textContent)).join(',')
          || clean(card.querySelector('.team-tags').textContent);
        const img = card.querySelector('.team-img-wrap img');
        const photo_url = card.dataset.photoUrl || (img ? img.getAttribute('src') : null);
        const payload = { name, role_title, bio, tags, photo_url, display_order: i, is_active: true };

        if (card.dataset.teamId) {
          await api(`/api/superadmin/team/${card.dataset.teamId}`, { method: 'PUT', body: JSON.stringify(payload) });
        } else {
          const created = await api('/api/superadmin/team/', { method: 'POST', body: JSON.stringify(payload) });
          card.dataset.teamId = String(created.member_id);
        }
      }

      const galleryGrid = document.getElementById('galleryGrid');
      const galleryItems = galleryGrid ? Array.from(galleryGrid.querySelectorAll('.gallery-item')) : [];
      for (let i = 0; i < galleryItems.length; i++) {
        const item = galleryItems[i];
        const clean = (s) => s.replace(/\s+/g, ' ').trim();
        const captionEl = item.querySelector('.gallery-overlay span');
        const caption = clean(captionEl ? captionEl.textContent : '');
        const img = item.querySelector('img');
        const image_url = item.dataset.photoUrl || (img ? img.getAttribute('src') : null);
        const payload = { image_url, caption, display_order: i, is_active: true };

        if (item.dataset.galleryId) {
          await api(`/api/superadmin/gallery/${item.dataset.galleryId}`, { method: 'PUT', body: JSON.stringify(payload) });
        } else {
          const created = await api('/api/superadmin/gallery/', { method: 'POST', body: JSON.stringify(payload) });
          item.dataset.galleryId = String(created.image_id);
        }
      }

      // Testimonials are patient-submitted; superadmin can only edit/remove
      // ones that already exist here, never create new ones (no "new"
      // branch, unlike team/gallery -- there's nothing to POST).
      const testiGrid = document.getElementById('testiGrid');
      const testiCards = testiGrid ? Array.from(testiGrid.querySelectorAll('.testi-card')) : [];
      for (let i = 0; i < testiCards.length; i++) {
        const card = testiCards[i];
        if (!card.dataset.testiId) continue;
        const clean = (s) => s.replace(/\s+/g, ' ').trim();
        const quote = clean(card.querySelector('.testi-text').textContent);
        const author_name = clean(card.querySelector('.testi-name strong').textContent);
        const author_role = clean(card.querySelector('.testi-name span').textContent);
        // Rating isn't inline-editable here -- read the star count back out
        // of the DOM so PUT doesn't silently reset it to the endpoint's
        // default of 5.
        const starsText = card.querySelector('.stars') ? card.querySelector('.stars').textContent : '';
        const rating = (starsText.match(/★/g) || []).length || 5;
        await api(`/api/superadmin/testimonials/${card.dataset.testiId}`, {
          method: 'PUT',
          body: JSON.stringify({ quote, author_name, author_role, rating, is_active: true, display_order: i }),
        });
      }

      statusEl.textContent = 'Saved — reloading…';
      setTimeout(() => { location.href = '/index.html?edit=1'; }, 700);
    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
    }
  }

  function addEditBar() {
    // When this page is embedded inside the superadmin's "Edit Landing
    // Page" admin shell (frontend/pages/superadmin/edit-landing.html),
    // there's already a real sidebar one level up for navigating away --
    // no Exit button needed, and it would only leave the admin area.
    const inIframe = window.self !== window.top;

    const bar = document.createElement('div');
    bar.className = 'pd-edit-bar';
    bar.innerHTML = `
      <span><i class="fas fa-pen-to-square"></i> Editing Landing Page</span>
      <span class="pd-status"></span>
      <button class="pd-save-btn"><i class="fas fa-check"></i> Save Changes</button>
      ${inIframe ? '' : '<button class="pd-exit-btn"><i class="fas fa-arrow-right-from-bracket"></i> Exit</button>'}
    `;
    document.body.appendChild(bar);
    const status = bar.querySelector('.pd-status');
    bar.querySelector('.pd-save-btn').addEventListener('click', () => saveAll(status));
    const exitBtn = bar.querySelector('.pd-exit-btn');
    if (exitBtn) exitBtn.addEventListener('click', () => { location.href = '/'; });
  }

  async function init() {
    let session;
    try {
      session = await (await fetch('/api/auth/session', { credentials: 'include' })).json();
    } catch (e) {
      return; // network error — silently skip edit mode
    }
    if (!session.authenticated || session.role !== 'superadmin') return;

    // Wait for site-content.js to finish populating the page first, so
    // the editor works on the real current values, not stale HTML.
    if (window.PerfectionsSiteContent) {
      await window.PerfectionsSiteContent.loadSiteContent();
    }

    injectStyle();
    setupFieldEditing();
    setupTeamEditing();
    setupGalleryEditing();
    setupTestimonialEditing();
    addEditBar();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
