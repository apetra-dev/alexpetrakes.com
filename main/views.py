from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
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
    """Contact form handler; redirects to homepage contact section."""
    logger.info("Contact page or form accessed")
    context = {
        "title": "Contact - Alex Petrakes",
    }

    if request.method == "GET":
        return redirect(reverse("home") + "#contact")

    if request.method == "POST":
        logger.info("Contact form submitted")
        # Get form data
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        logger.debug(
            f"Form data received - Name: {name}, Email: {email}, Subject: {subject}"
        )

        # Basic validation
        if name and email and subject and message:
            # Here you can add email sending functionality
            # For example, using Django's send_mail:
            # from django.core.mail import send_mail
            # send_mail(
            #     subject=f'Contact Form: {subject}',
            #     message=f'From: {name} ({email})\n\n{message}',
            #     from_email=email,
            #     recipient_list=['your-email@example.com'],
            #     fail_silently=False,
            # )

            logger.info("Contact form validation passed")
            messages.success(
                request, "Thank you for your message! I'll get back to you soon."
            )
            return redirect(reverse("home") + "#contact")
        else:
            logger.warning("Contact form validation failed - missing fields")
            messages.error(request, "Please fill in all fields.")
            return redirect(reverse("home") + "#contact")

    return redirect(reverse("home") + "#contact")
