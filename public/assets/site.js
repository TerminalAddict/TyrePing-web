const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#site-navigation');
function closeMenu() {
  menuButton?.setAttribute('aria-expanded', 'false');
  navigation?.classList.remove('is-open');
}
menuButton?.addEventListener('click', () => {
  const expanded = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!expanded));
  navigation?.classList.toggle('is-open', !expanded);
});
navigation?.addEventListener('click', (event) => {
  if (event.target.closest('a')) closeMenu();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && menuButton?.getAttribute('aria-expanded') === 'true') {
    closeMenu();
    menuButton.focus();
  }
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('.site-header')) closeMenu();
});
window.matchMedia('(min-width: 901px)').addEventListener('change', closeMenu);

const screenshotBrowser = document.querySelector('.screenshot-browser');
if (screenshotBrowser) {
  const choices = [...screenshotBrowser.querySelectorAll('[data-capture]')];
  const captures = [...screenshotBrowser.querySelectorAll('.app-capture')];
  const status = document.querySelector('#screenshot-status');
  function selectCapture(choice, announce = true) {
    choices.forEach((button) => button.setAttribute('aria-pressed', String(button === choice)));
    captures.forEach((capture) => {
      capture.hidden = capture.id !== choice.dataset.capture;
    });
    if (announce && status) {
      status.textContent = `Showing ${choice.querySelector('strong').textContent} screenshot.`;
    }
  }
  if (choices.length && captures.length) {
    selectCapture(choices[0], false);
    screenshotBrowser.classList.add('is-enhanced');
    screenshotBrowser.querySelector('.screenshot-controls').hidden = false;
    choices.forEach((choice) => choice.addEventListener('click', () => selectCapture(choice)));
  }
}

const screenshotModal = document.querySelector('#screenshot-modal');
if (screenshotBrowser && screenshotModal && typeof screenshotModal.showModal === 'function') {
  const images = [...screenshotBrowser.querySelectorAll('.app-capture')].map((capture) => ({
    id: capture.id,
    source: capture.querySelector('.capture-image').href,
    title: capture.querySelector('h3').textContent,
    description: capture.querySelector('figcaption p').textContent,
    alt: capture.querySelector('img').alt,
  }));
  const image = screenshotModal.querySelector('.modal-image');
  const imageArea = screenshotModal.querySelector('.modal-image-area');
  const title = screenshotModal.querySelector('#screenshot-modal-title');
  const caption = screenshotModal.querySelector('#screenshot-modal-caption');
  const counter = screenshotModal.querySelector('.modal-counter');
  const announcement = screenshotModal.querySelector('.modal-announcement');
  const zoomButton = screenshotModal.querySelector('[data-modal-zoom]');
  const closeButton = screenshotModal.querySelector('[data-modal-close]');
  let currentIndex = 0;
  let opener;
  let touchStart;

  function resetZoom() {
    imageArea.classList.remove('is-zoomed');
    zoomButton.setAttribute('aria-pressed', 'false');
    zoomButton.textContent = 'Zoom in';
    imageArea.scrollTo(0, 0);
  }

  function showImage(index) {
    currentIndex = (index + images.length) % images.length;
    const capture = images[currentIndex];
    resetZoom();
    image.alt = capture.alt;
    image.src = capture.source;
    title.textContent = capture.title;
    caption.textContent = capture.description;
    counter.textContent = `${currentIndex + 1} / ${images.length}`;
    announcement.textContent = `${capture.title}, screenshot ${currentIndex + 1} of ${images.length}.`;
  }

  document.querySelectorAll('.capture-image, .capture-full, [data-screenshot]').forEach((link) => {
    const captureId = link.dataset.screenshot || link.closest('.app-capture')?.id;
    const index = images.findIndex((capture) => capture.id === captureId);
    if (index < 0) return;
    link.setAttribute('aria-haspopup', 'dialog');
    link.setAttribute('aria-controls', 'screenshot-modal');
    link.addEventListener('click', (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = link;
      showImage(index);
      document.documentElement.classList.add('screenshot-modal-open');
      screenshotModal.showModal();
      closeButton.focus({ preventScroll: true });
    });
  });

  screenshotModal.querySelector('[data-modal-previous]').addEventListener('click', () => showImage(currentIndex - 1));
  screenshotModal.querySelector('[data-modal-next]').addEventListener('click', () => showImage(currentIndex + 1));
  closeButton.addEventListener('click', () => screenshotModal.close());
  zoomButton.addEventListener('click', () => {
    const zoomed = imageArea.classList.toggle('is-zoomed');
    zoomButton.setAttribute('aria-pressed', String(zoomed));
    zoomButton.textContent = zoomed ? 'Fit to screen' : 'Zoom in';
    imageArea.scrollTop = 0;
    imageArea.scrollLeft = zoomed ? (imageArea.scrollWidth - imageArea.clientWidth) / 2 : 0;
  });
  screenshotModal.addEventListener('keydown', (event) => {
    if (event.key === 'Tab') {
      const focusable = [...screenshotModal.querySelectorAll('button, [tabindex="0"]')];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey || imageArea.classList.contains('is-zoomed')) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      showImage(currentIndex + (event.key === 'ArrowLeft' ? -1 : 1));
    }
  });
  // Keep image panning and pinch zoom available; recognise horizontal swipes only in fit mode.
  imageArea.addEventListener('touchstart', (event) => {
    touchStart = event.touches.length === 1 && !imageArea.classList.contains('is-zoomed')
      ? { x: event.touches[0].clientX, y: event.touches[0].clientY }
      : null;
  }, { passive: true });
  imageArea.addEventListener('touchmove', (event) => {
    if (event.touches.length !== 1) touchStart = null;
  }, { passive: true });
  imageArea.addEventListener('touchend', (event) => {
    if (!touchStart || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      showImage(currentIndex + (dx < 0 ? 1 : -1));
    }
  }, { passive: true });
  imageArea.addEventListener('touchcancel', () => { touchStart = null; }, { passive: true });

  let backdropPointerDown = false;
  screenshotModal.addEventListener('pointerdown', (event) => {
    backdropPointerDown = event.target === screenshotModal;
  });
  screenshotModal.addEventListener('click', (event) => {
    if (backdropPointerDown && event.target === screenshotModal) screenshotModal.close();
    backdropPointerDown = false;
  });
  screenshotModal.addEventListener('close', () => {
    document.documentElement.classList.remove('screenshot-modal-open');
    touchStart = null;
    opener?.focus({ preventScroll: true });
  });
}
