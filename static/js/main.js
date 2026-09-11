// alexpetrakes.com: nav scroll state, current-section highlighting, and a submit
// guard on the contact form. Scrolling itself is CSS
// (scroll-behavior + scroll-padding-top), so nothing here is required for layout.
(function () {
    'use strict';

    var nav = document.querySelector('[data-nav]');
    if (nav) {
        var onScroll = function () {
            nav.classList.toggle('is-scrolled', window.scrollY > 24);
        };
        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });
    }

    var links = Array.prototype.slice.call(document.querySelectorAll('[data-section-link]'));
    var sections = links
        .map(function (a) { return document.querySelector(a.getAttribute('href')); })
        .filter(Boolean);

    if ('IntersectionObserver' in window && sections.length) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) { return; }
                links.forEach(function (a) {
                    a.classList.toggle('is-current', a.getAttribute('href') === '#' + entry.target.id);
                });
            });
        }, { rootMargin: '-40% 0px -55% 0px', threshold: 0 });
        sections.forEach(function (s) { observer.observe(s); });
    }

    var form = document.querySelector('form[data-contact]');
    if (form) {
        form.addEventListener('submit', function () {
            var button = form.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
                button.textContent = 'Sending';
            }
        });
    }
})();
