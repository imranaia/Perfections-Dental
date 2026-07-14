// loading.js
const LoadingManager = {
  overlay: null,
  
  init() {
    // Create overlay if it doesn't exist
    if (!document.getElementById('loadingOverlay')) {
      this.createOverlay();
    }
    this.overlay = document.getElementById('loadingOverlay');
    
    // Auto-hide when page is ready
    document.addEventListener('DOMContentLoaded', () => {
      this.waitForPageLoad();
    });
    
    // Handle page cache
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) {
        this.show();
        setTimeout(() => this.hide(), 800);
      }
    });
  },
  
  createOverlay() {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.id = 'loadingOverlay';
    overlay.innerHTML = `
      <div class="loading-content">
        <div class="loading-logo-3d">
          <img src="../../assets/logo.png" alt="Perfections Dental" />
        </div>
        <div class="loading-spinner"></div>
        <div class="loading-text">Perfections Dental Services</div>
      </div>
    `;
    document.body.appendChild(overlay);
  },
  
  show() {
    if (this.overlay) {
      this.overlay.classList.remove('hide');
      document.body.classList.add('loading-active');
    }
  },
  
  hide() {
    if (this.overlay) {
      this.overlay.classList.add('hide');
      document.body.classList.remove('loading-active');
    }
  },
  
  waitForPageLoad(options = { minTime: 2000, maxTime: 6000 }) {
    const startTime = Date.now();
    
    Promise.all([
      // Wait for images
      new Promise(resolve => {
        const images = document.querySelectorAll('img');
        if (images.length === 0) return resolve();
        
        const imagePromises = Array.from(images).map(img => {
          if (img.complete) return Promise.resolve();
          return new Promise(resolve => {
            img.onload = resolve;
            img.onerror = resolve;
          });
        });
        Promise.all(imagePromises).then(resolve);
      }),
      // Wait for minimum time
      new Promise(resolve => {
        const elapsed = Date.now() - startTime;
        const waitTime = Math.max(0, options.minTime - elapsed);
        setTimeout(resolve, waitTime);
      })
    ]).then(() => this.hide());
    
    // Max time fallback
    setTimeout(() => this.hide(), options.maxTime);
  }
};

// Initialize on page load
LoadingManager.init();