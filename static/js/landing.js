/**
 * DocChat — Landing Page JS
 * Handles: scroll reveal, sticky navbar, smooth anchors, mock UI typing animation
 */

(function () {
  'use strict';

  /* ── 1. Sticky Navbar ───────────────────────────────── */
  const nav = document.getElementById('lp-nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 60) {
        nav.classList.add('lp-nav--scrolled');
      } else {
        nav.classList.remove('lp-nav--scrolled');
      }
    }, { passive: true });
  }

  /* ── 2. Mobile hamburger toggle ─────────────────────── */
  const hamburger = document.getElementById('lp-hamburger');
  const mobileMenu = document.getElementById('lp-mobile-menu');
  if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
      const isOpen = mobileMenu.classList.contains('open');
      hamburger.setAttribute('aria-expanded', isOpen);
      if (nav) {
        if (isOpen) {
          nav.classList.add('lp-nav--menu-open');
        } else {
          nav.classList.remove('lp-nav--menu-open');
        }
      }
    });
    // Close menu on link click
    mobileMenu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        mobileMenu.classList.remove('open');
        if (nav) {
          nav.classList.remove('lp-nav--menu-open');
        }
      });
    });
  }

  /* ── 3. Smooth scroll for anchor links ──────────────── */
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (target) {
        e.preventDefault();
        const offset = 80; // navbar height
        const top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });

  /* ── 4. Scroll reveal (IntersectionObserver) ────────── */
  const revealItems = document.querySelectorAll('.fade-in-up');
  if (revealItems.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });

    revealItems.forEach(item => observer.observe(item));
  } else {
    // Fallback: show all immediately
    revealItems.forEach(item => item.classList.add('visible'));
  }

  /* ── 5. Mock UI typing animation ────────────────────── */
  const typingIndicator = document.getElementById('mock-typing');
  const aiResponseEl = document.getElementById('mock-ai-response');

  if (typingIndicator && aiResponseEl) {
    // Show typing for 2s then reveal the AI response
    setTimeout(() => {
      typingIndicator.style.transition = 'opacity 0.3s ease';
      typingIndicator.style.opacity = '0';
      setTimeout(() => {
        typingIndicator.style.display = 'none';
        aiResponseEl.style.display = 'flex';
        aiResponseEl.style.opacity = '0';
        aiResponseEl.style.transition = 'opacity 0.5s ease';
        // Force reflow then fade in
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            aiResponseEl.style.opacity = '1';
          });
        });
      }, 300);
    }, 2000);
  }

  /* ── 6. Theme Toggle (Desktop & Mobile) ──────────────── */
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  const mobileThemeToggle = document.getElementById('mobile-theme-toggle');
  const mobileThemeIcon = document.getElementById('mobile-theme-icon');

  function updateThemeIcons(theme) {
    if (theme === 'light') {
      if (themeIcon) {
        themeIcon.classList.remove('bi-moon');
        themeIcon.classList.add('bi-sun');
      }
      if (mobileThemeIcon) {
        mobileThemeIcon.classList.remove('bi-moon');
        mobileThemeIcon.classList.add('bi-sun');
      }
    } else {
      if (themeIcon) {
        themeIcon.classList.remove('bi-sun');
        themeIcon.classList.add('bi-moon');
      }
      if (mobileThemeIcon) {
        mobileThemeIcon.classList.remove('bi-sun');
        mobileThemeIcon.classList.add('bi-moon');
      }
    }
  }

  function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcons(newTheme);
  }

  const initialTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  updateThemeIcons(initialTheme);

  if (themeToggle) {
    themeToggle.addEventListener('click', (e) => {
      e.preventDefault();
      toggleTheme();
    });
  }

  if (mobileThemeToggle) {
    mobileThemeToggle.addEventListener('click', (e) => {
      e.preventDefault();
      toggleTheme();
    });
  }

})();