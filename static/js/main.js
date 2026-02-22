// Main JavaScript for Alex Petrakes website
// Handles navigation, scroll animations, and form interactions

document.addEventListener('DOMContentLoaded', function() {
    console.log('Website loaded');
    
    console.log('Navigation links displayed inline on all screen sizes');

    // Image loading with fallback
    const heroImage = document.getElementById('heroImage');
    if (heroImage) {
        console.log('Hero image element found');
        
        setTimeout(() => {
            if (heroImage.style.opacity === '' || heroImage.style.opacity === '0') {
                heroImage.style.opacity = '1';
                heroImage.style.transform = 'scale(1)';
                console.log('Image visibility enforced via timeout');
            }
        }, 3000);
        
        heroImage.addEventListener('error', function() {
            console.log('Hero image failed to load, checking for fallback');
            if (this.src && !this.src.includes('mountain-peak')) {
                const fallbackPath = this.src.replace('profile.jpg', 'mountain-peak.jpeg');
                this.src = fallbackPath;
                console.log('Fallback image applied');
            }
            this.style.opacity = '1';
        });
        
        if (heroImage.complete && heroImage.naturalHeight !== 0) {
            console.log('Image already loaded');
        } else {
            heroImage.addEventListener('load', function() {
                console.log('Image loaded successfully');
            });
        }
    }

    // Scroll-triggered animations for about section
    const aboutImageCol = document.querySelector('.about-image-col');
    const aboutTextCol = document.querySelector('.about-text-col');
    const aboutSections = document.querySelectorAll('.about-text-section');
    const aboutValuesColumn = document.querySelector('.about-values-column');
    
    const elementsToObserve = [];
    if (aboutImageCol) elementsToObserve.push(aboutImageCol);
    if (aboutTextCol) elementsToObserve.push(aboutTextCol);
    aboutSections.forEach(section => elementsToObserve.push(section));
    if (aboutValuesColumn) elementsToObserve.push(aboutValuesColumn);

    if (elementsToObserve.length > 0) {
        console.log(`Setting up scroll observer for ${elementsToObserve.length} elements`);
        
        const observerOptions = {
            threshold: 0.2,
            rootMargin: '0px 0px -50px 0px'
        };

        const scrollObserver = new IntersectionObserver(function(entries) {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    console.log('Element became visible:', entry.target.className.split(' ')[0]);
                }
            });
        }, observerOptions);

        elementsToObserve.forEach((el, index) => {
            el.style.transitionDelay = `${index * 0.1}s`;
            scrollObserver.observe(el);
            console.log(`Observing element: ${el.className.split(' ')[0]}`);
        });
    }

    // Navbar scroll effect
    const navbar = document.querySelector('.navbar');
    
    if (navbar) {
        console.log('Navbar scroll listener attached');
        window.addEventListener('scroll', () => {
            const currentScroll = window.pageYOffset;
            
            if (currentScroll > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }

    // Contact form handling
    const contactForm = document.querySelector('.contact-form');
    if (contactForm) {
        console.log('Contact form found, attaching submit handler');
        contactForm.addEventListener('submit', function(e) {
            const submitButton = this.querySelector('.btn-submit');
            if (submitButton) {
                submitButton.style.opacity = '0.6';
                submitButton.disabled = true;
                console.log('Form submitted, button disabled');
            }
        });
    }

    function getNavbarHeight() {
        var nav = document.querySelector('.navbar');
        return nav ? nav.offsetHeight : 0;
    }

    function smoothScrollTo(target) {
        var offset = getNavbarHeight();
        var top = target.getBoundingClientRect().top + window.pageYOffset - offset;
        window.scrollTo({ top: top, behavior: 'smooth' });
    }

    // Smooth scroll for anchor links (hash-only and full URL with hash)
    document.querySelectorAll('.nav-link, .footer-links a').forEach(link => {
        link.addEventListener('click', function (e) {
            var href = this.getAttribute('href') || '';
            var hashMatch = href.match(/#([a-z]+)$/);
            if (hashMatch && (window.location.pathname === '/' || window.location.pathname === '')) {
                var id = hashMatch[1];
                var target = document.getElementById(id);
                if (target) {
                    e.preventDefault();
                    smoothScrollTo(target);
                    window.history.pushState(null, '', '#' + id);
                    console.log('Smooth scrolled to section:', id);
                }
            }
        });
    });

    // Smooth scroll for hash-only anchor links (e.g. #contact from CTA button)
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            var targetId = this.getAttribute('href').slice(1);
            if (!targetId) return;
            var target = document.getElementById(targetId);
            if (target) {
                e.preventDefault();
                smoothScrollTo(target);
                console.log('Smooth scrolled to:', targetId);
            }
        });
    });

    // On load, scroll to section if URL has hash (e.g. after redirect from form)
    if (window.location.hash) {
        var id = window.location.hash.slice(1);
        var target = document.getElementById(id);
        if (target) {
            setTimeout(function () {
                smoothScrollTo(target);
                console.log('Scrolled to hash on load:', id);
            }, 100);
        }
    }
    
    console.log('JavaScript initialization complete');
});
