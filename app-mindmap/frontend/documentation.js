(function(){
  'use strict';

  const nav = document.getElementById('docNav');
  const progressBar = document.getElementById('docProgressBar');
  const dots = document.querySelectorAll('.doc-dot');
  const slides = document.querySelectorAll('.doc-slide');

  let lastScrollY = 0;
  let ticking = false;

  function isInView(el, offset){
    const rect = el.getBoundingClientRect();
    const threshold = offset || 0.3;
    return rect.top < window.innerHeight * (1 - threshold) && rect.bottom > threshold * window.innerHeight;
  }

  function getActiveIndex(){
    let active = 0;
    slides.forEach((slide, i) => {
      const rect = slide.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      if (mid < window.innerHeight && mid > 0){
        active = i;
      } else if (rect.top < 0 && rect.bottom > 0){
        active = i;
      }
    });
    return active;
  }

  function updateProgress(){
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    progressBar.style.width = pct + '%';
  }

  function updateSlideVisibility(){
    slides.forEach(slide => {
      if (isInView(slide, 0.25)){
        slide.classList.add('visible');
      }
    });

    document.querySelectorAll('.doc-card-type, .doc-feature-item, .doc-col, .doc-visual-row, .doc-tags-demo, .doc-shortcut-group').forEach(el => {
      if (isInView(el, 0.15)){
        el.classList.add('visible');
      }
    });
  }

  function updateNav(){
    const scrollY = window.scrollY;
    if (scrollY > 120){
      if (scrollY > lastScrollY){
        nav.classList.add('hidden');
      } else {
        nav.classList.remove('hidden');
      }
    } else {
      nav.classList.remove('hidden');
    }
    lastScrollY = scrollY;
  }

  function updateDots(){
    const active = getActiveIndex();
    dots.forEach((dot, i) => {
      dot.classList.toggle('active', i === active);
    });
  }

  function onScroll(){
    if (!ticking){
      requestAnimationFrame(() => {
        updateProgress();
        updateSlideVisibility();
        updateNav();
        updateDots();
        ticking = false;
      });
      ticking = true;
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });

  dots.forEach(dot => {
    dot.addEventListener('click', () => {
      const target = document.getElementById(dot.dataset.target);
      if (target){
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  document.querySelectorAll('.doc-nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const href = link.getAttribute('href');
      if (href && href.startsWith('#')){
        const target = document.querySelector(href);
        if (target){
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    });
  });

  const heroAnimation = () => {
    const heroContent = document.querySelector('#overview .doc-slide-content');
    if (heroContent){
      heroContent.style.opacity = '1';
      heroContent.querySelectorAll(':scope > *').forEach(el => {
        el.style.opacity = '';
        el.style.transform = '';
      });
    }
  };

  if (document.fonts && document.fonts.ready){
    document.fonts.ready.then(heroAnimation);
  } else {
    heroAnimation();
  }

  setTimeout(() => {
    onScroll();
  }, 100);

  onScroll();
})();