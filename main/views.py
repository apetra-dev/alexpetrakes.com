from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def home(request):
    """Home page view with entrance animation and slow image reveal"""
    logger.info("Home page accessed")
    context = {
        "title": "Alex Petrakes",
        "body_class": "page-home",
    }
    return render(request, "main/home.html", context)


def contact(request):
    """Contact form handler; sends email and redirects to homepage contact section."""
    logger.info("Contact page or form accessed")

    if request.method == "GET":
        return redirect(reverse("home") + "#contact")

    if request.method == "POST":
        logger.info("Contact form submitted")
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message_body = request.POST.get("message", "").strip()

        logger.debug(
            f"Form data received - Name: {name}, Email: {email}, Subject: {subject}"
        )

        if not all([name, email, subject, message_body]):
            logger.warning("Contact form validation failed - missing fields")
            messages.error(request, "Please fill in all fields.")
            return redirect(reverse("home") + "#contact")

        full_message = (
            f"New contact form submission from alexpetrakes.com\n"
            f"{'=' * 50}\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Subject: {subject}\n\n"
            f"Message:\n{message_body}\n"
        )

        try:
            send_mail(
                subject=f"[alexpetrakes.com] {subject}",
                message=full_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_EMAIL],
                fail_silently=False,
            )
            logger.info(f"Contact email sent successfully - from {name} ({email})")
            messages.success(
                request,
                "Thank you for your message! I'll get back to you soon.",
            )
        except Exception:
            logger.exception("Failed to send contact form email")
            messages.error(
                request,
                "Sorry, there was a problem sending your message. "
                "Please try emailing me directly at apetrakes1@gmail.com.",
            )

        return redirect(reverse("home") + "#contact")

    return redirect(reverse("home") + "#contact")
