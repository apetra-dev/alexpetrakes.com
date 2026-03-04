from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
import logging

from .models import PendingContact

logger = logging.getLogger(__name__)

VERIFICATION_EXPIRY_HOURS = 24


def home(request):
    """Home page view with entrance animation and slow image reveal"""
    logger.info("Home page accessed")
    context = {
        "title": "Alex Petrakes",
        "body_class": "page-home",
    }
    return render(request, "main/home.html", context)


def contact(request):
    """Contact form handler. Saves the submission and sends a verification email to the sender."""
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

        pending = PendingContact.objects.create(
            name=name,
            email=email,
            subject=subject,
            message=message_body,
        )
        logger.info(f"PendingContact created - id: {pending.id}, from {name} ({email})")

        verify_url = request.build_absolute_uri(
            reverse("verify_contact", kwargs={"token": pending.id})
        )
        logger.debug(f"Verification URL built: {verify_url}")

        verification_body = render_to_string(
            "main/emails/verification_email.txt",
            {"name": name, "verify_url": verify_url},
        )

        try:
            send_mail(
                subject="Please verify your email — alexpetrakes.com",
                message=verification_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info(f"Verification email sent to {email}")
            messages.success(
                request,
                "Almost there! Check your inbox for a verification email and click the link to send your message.",
            )
        except Exception:
            logger.exception(
                f"Failed to send verification email to {email} for PendingContact {pending.id}"
            )
            pending.delete()
            logger.info(
                f"PendingContact {pending.id} deleted after failed verification email"
            )
            messages.error(
                request,
                "Sorry, there was a problem sending the verification email. "
                "Please try again or email me directly at apetrakes1@gmail.com.",
            )

        return redirect(reverse("home") + "#contact")

    return redirect(reverse("home") + "#contact")


def verify_contact(request, token):
    """
    Handles email verification links. Looks up the PendingContact by token (UUID pk),
    checks expiry, sends the real notification email to the site owner, then deletes the record.
    """
    logger.info(f"Email verification attempt for token: {token}")

    try:
        pending = PendingContact.objects.get(pk=token)
    except PendingContact.DoesNotExist:
        logger.warning(f"Verification token not found: {token}")
        messages.error(
            request,
            "This verification link is invalid. "
            "Please submit the contact form again.",
        )
        return redirect(reverse("home") + "#contact")

    age_hours = (timezone.now() - pending.created_at).total_seconds() / 3600
    logger.debug(
        f"PendingContact {token} age: {age_hours:.2f} hours "
        f"(expiry: {VERIFICATION_EXPIRY_HOURS}h)"
    )

    if age_hours > VERIFICATION_EXPIRY_HOURS:
        logger.warning(f"Verification token expired: {token} (age: {age_hours:.2f}h)")
        pending.delete()
        logger.info(f"Expired PendingContact {token} deleted")
        messages.error(
            request,
            "This verification link has expired (links are valid for 24 hours). "
            "Please submit the contact form again.",
        )
        return redirect(reverse("home") + "#contact")

    notification_body = render_to_string(
        "main/emails/contact_notification.txt",
        {
            "name": pending.name,
            "email": pending.email,
            "subject": pending.subject,
            "message": pending.message,
        },
    )

    try:
        send_mail(
            subject=f"[alexpetrakes.com] {pending.subject}",
            message=notification_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=False,
        )
        logger.info(
            f"Contact notification sent to site owner for PendingContact {token} "
            f"from {pending.name} ({pending.email})"
        )
    except Exception:
        logger.exception(
            f"Failed to send contact notification for PendingContact {token}"
        )
        messages.error(
            request,
            "Sorry, there was a problem delivering your message. "
            "Please try again or email me directly at apetrakes1@gmail.com.",
        )
        return redirect(reverse("home") + "#contact")

    pending.delete()
    logger.info(f"PendingContact {token} deleted after successful delivery")

    messages.success(
        request,
        "Your email has been verified and your message has been sent! I'll get back to you soon.",
    )
    return redirect(reverse("home") + "#contact")
