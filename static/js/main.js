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
        var loadedAt = Date.now();
        var setClient = function (name, value) {
            var field = form.querySelector('[data-client="' + name + '"]');
            if (field && value !== undefined && value !== null && value !== '') {
                field.value = String(value).slice(0, 200);
            }
        };
        var describe = function () {
            try {
                var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                setClient('timezone', tz);
            } catch (e) { /* older engines */ }
            setClient('utc_offset', -new Date().getTimezoneOffset());
            setClient('languages', (navigator.languages || [navigator.language]).join(','));
            setClient('screen', screen.width + 'x' + screen.height + '@' + (window.devicePixelRatio || 1));
            setClient('viewport', window.innerWidth + 'x' + window.innerHeight);
            var uaData = navigator.userAgentData;
            setClient('platform', (uaData && uaData.platform) || navigator.platform || '');
            setClient('touch', navigator.maxTouchPoints || 0);
            if (window.matchMedia) {
                setClient('color_scheme', window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            }
        };
        describe();

        form.addEventListener('submit', function () {
            setClient('dwell', Math.round((Date.now() - loadedAt) / 1000));
            var button = form.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
                button.textContent = 'Sending';
            }
        });
    }
})();
