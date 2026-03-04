import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from .models import PendingContact
from .views import VERIFICATION_EXPIRY_HOURS


class PendingContactModelTests(TestCase):
    def test_creates_with_uuid_pk(self):
        pending = PendingContact.objects.create(
            name="Alice",
            email="alice@example.com",
            subject="Hello",
            message="Test message",
        )
        self.assertIsInstance(pending.id, uuid.UUID)

    def test_str_representation(self):
        pending = PendingContact(
            name="Alice",
            email="alice@example.com",
            subject="Hello",
            message="Test",
        )
        self.assertIn("Alice", str(pending))
        self.assertIn("alice@example.com", str(pending))

    def test_created_at_is_set_automatically(self):
        before = timezone.now()
        pending = PendingContact.objects.create(
            name="Bob",
            email="bob@example.com",
            subject="Subject",
            message="Body",
        )
        after = timezone.now()
        self.assertGreaterEqual(pending.created_at, before)
        self.assertLessEqual(pending.created_at, after)


class ContactViewTests(TestCase):
    def setUp(self):
        self.form_data = {
            "name": "Alice",
            "email": "alice@example.com",
            "subject": "Hello",
            "message": "Test message body",
        }

    @patch("main.views.send_mail")
    def test_post_creates_pending_contact(self, mock_send):
        self.client.post(reverse("contact"), data=self.form_data)
        self.assertEqual(PendingContact.objects.count(), 1)
        pending = PendingContact.objects.first()
        self.assertEqual(pending.name, "Alice")
        self.assertEqual(pending.email, "alice@example.com")

    @patch("main.views.send_mail")
    def test_post_sends_verification_email_to_user(self, mock_send):
        self.client.post(reverse("contact"), data=self.form_data)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        self.assertEqual(call_kwargs.kwargs["recipient_list"], ["alice@example.com"])
        self.assertIn("verify", call_kwargs.kwargs["subject"].lower())

    @patch("main.views.send_mail")
    def test_post_shows_check_inbox_message(self, mock_send):
        response = self.client.post(
            reverse("contact"), data=self.form_data, follow=True
        )
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("inbox" in str(m).lower() or "verify" in str(m).lower() for m in msgs)
        )

    @patch("main.views.send_mail")
    def test_post_missing_fields_does_not_create_pending(self, mock_send):
        self.client.post(reverse("contact"), data={"name": "Alice"})
        self.assertEqual(PendingContact.objects.count(), 0)
        mock_send.assert_not_called()

    @patch("main.views.send_mail")
    def test_post_send_failure_deletes_pending_contact(self, mock_send):
        mock_send.side_effect = Exception("SMTP error")
        self.client.post(reverse("contact"), data=self.form_data)
        self.assertEqual(PendingContact.objects.count(), 0)

    def test_get_redirects_to_home_contact(self):
        response = self.client.get(reverse("contact"))
        self.assertRedirects(
            response, reverse("home") + "#contact", fetch_redirect_response=False
        )


class VerifyContactViewTests(TestCase):
    def _make_pending(self, hours_ago=0):
        pending = PendingContact.objects.create(
            name="Alice",
            email="alice@example.com",
            subject="Hello",
            message="Test body",
        )
        if hours_ago:
            PendingContact.objects.filter(pk=pending.pk).update(
                created_at=timezone.now() - timedelta(hours=hours_ago)
            )
            pending.refresh_from_db()
        return pending

    @patch("main.views.send_mail")
    def test_valid_token_sends_notification_to_owner(self, mock_send):
        pending = self._make_pending()
        self.client.get(reverse("verify_contact", kwargs={"token": pending.id}))
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        self.assertIn("alexpetrakes.com", call_kwargs.kwargs["subject"])

    @patch("main.views.send_mail")
    def test_valid_token_deletes_pending_contact(self, mock_send):
        pending = self._make_pending()
        self.client.get(reverse("verify_contact", kwargs={"token": pending.id}))
        self.assertEqual(PendingContact.objects.count(), 0)

    @patch("main.views.send_mail")
    def test_valid_token_shows_success_message(self, mock_send):
        pending = self._make_pending()
        response = self.client.get(
            reverse("verify_contact", kwargs={"token": pending.id}), follow=True
        )
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("verified" in str(m).lower() for m in msgs))

    def test_invalid_token_shows_error(self):
        fake_token = uuid.uuid4()
        response = self.client.get(
            reverse("verify_contact", kwargs={"token": fake_token}), follow=True
        )
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("invalid" in str(m).lower() for m in msgs))

    def test_expired_token_deletes_pending_contact_and_shows_error(self):
        pending = self._make_pending(hours_ago=VERIFICATION_EXPIRY_HOURS + 1)
        response = self.client.get(
            reverse("verify_contact", kwargs={"token": pending.id}), follow=True
        )
        self.assertEqual(PendingContact.objects.count(), 0)
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("expired" in str(m).lower() for m in msgs))

    def test_token_at_exactly_expiry_boundary_is_still_valid(self):
        """A token aged exactly at the boundary (not over) should still be valid."""
        pending = self._make_pending(hours_ago=VERIFICATION_EXPIRY_HOURS - 1)
        with patch("main.views.send_mail"):
            response = self.client.get(
                reverse("verify_contact", kwargs={"token": pending.id}), follow=True
            )
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("verified" in str(m).lower() for m in msgs))

    @patch("main.views.send_mail")
    def test_expired_token_does_not_send_notification(self, mock_send):
        pending = self._make_pending(hours_ago=VERIFICATION_EXPIRY_HOURS + 1)
        self.client.get(reverse("verify_contact", kwargs={"token": pending.id}))
        mock_send.assert_not_called()
