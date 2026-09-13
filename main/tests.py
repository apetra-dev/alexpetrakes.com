import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import sender_intel
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


@override_settings(SENDER_INTEL_ENABLED=False)
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
    def test_post_captures_sender_context(self, mock_send):
        self.client.get(reverse("home"), HTTP_REFERER="https://news.ycombinator.com/item?id=1")
        data = dict(
            self.form_data,
            client_timezone="Europe/Berlin",
            client_languages="de-DE,de,en",
            client_screen="1920x1080@1",
            client_dwell="37",
        )
        self.client.post(
            reverse("contact"),
            data=data,
            HTTP_X_FORWARDED_FOR="8.8.8.8, 10.0.0.1",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/130.0",
            HTTP_ACCEPT_LANGUAGE="de-DE,de;q=0.9",
        )
        pending = PendingContact.objects.get()
        self.assertEqual(pending.submitted_ip, "8.8.8.8")
        meta = pending.submission_meta
        self.assertEqual(meta["ip"], "8.8.8.8")
        self.assertEqual(meta["headers"]["accept_language"], "de-DE,de;q=0.9")
        self.assertIn("Firefox", meta["headers"]["user_agent"])
        self.assertEqual(meta["client"]["timezone"], "Europe/Berlin")
        self.assertEqual(meta["client"]["dwell"], "37")
        self.assertEqual(meta["session"]["landing_referer"], "https://news.ycombinator.com/item?id=1")
        self.assertEqual(meta["session"]["visits"], 1)
        self.assertIn("first_seen", meta["session"])

    @patch("main.views.send_mail")
    def test_honeypot_filled_stores_nothing_but_looks_successful(self, mock_send):
        response = self.client.post(
            reverse("contact"), data=dict(self.form_data, website="http://spam.example"), follow=True
        )
        self.assertEqual(PendingContact.objects.count(), 0)
        mock_send.assert_not_called()
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("check your inbox" in str(m).lower() for m in msgs))

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


@override_settings(SENDER_INTEL_ENABLED=False)
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
    def test_valid_token_marks_pending_contact_delivered(self, mock_send):
        pending = self._make_pending()
        self.client.get(reverse("verify_contact", kwargs={"token": pending.id}))
        pending.refresh_from_db()
        self.assertIsNotNone(pending.verified_at)
        self.assertIsNotNone(pending.delivered_at)
        self.assertEqual(pending.status, "delivered")

    @patch("main.views.send_mail")
    def test_reused_link_does_not_resend(self, mock_send):
        pending = self._make_pending()
        url = reverse("verify_contact", kwargs={"token": pending.id})
        self.client.get(url)
        response = self.client.get(url, follow=True)
        mock_send.assert_called_once()
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any("already" in str(m).lower() for m in msgs))

    @patch("main.views.send_mail")
    def test_notification_includes_sender_report(self, mock_send):
        pending = self._make_pending()
        PendingContact.objects.filter(pk=pending.pk).update(
            submitted_ip="8.8.8.8",
            submission_meta={
                "ip": "8.8.8.8",
                "headers": {
                    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "accept_language": "en-US,en;q=0.9",
                },
                "client": {"timezone": "America/New_York", "screen": "1512x982@2", "dwell": "45"},
                "session": {"first_seen": "2026-09-12T10:00:00+00:00", "landing_referer": "https://www.linkedin.com/in/apetrakes/", "visits": 3},
                "at": "2026-09-12T10:06:00+00:00",
            },
        )
        self.client.get(
            reverse("verify_contact", kwargs={"token": pending.id}),
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        )
        body = mock_send.call_args.kwargs["message"]
        self.assertIn("About the sender", body)
        self.assertIn("8.8.8.8", body)
        self.assertIn("Chrome 128 on macOS 10.15.7 (desktop)", body)
        self.assertIn("America/New_York", body)
        self.assertIn("linkedin.com", body)
        self.assertIn("1.1.1.1", body)
        self.assertIn("Safari 17.5 on iOS 17.5 (phone)", body)
        self.assertIn("different address", body)
        pending.refresh_from_db()
        self.assertEqual(pending.verified_ip, "1.1.1.1")

    @patch("main.views.send_mail")
    def test_report_failure_does_not_block_delivery(self, mock_send):
        pending = self._make_pending()
        with patch("main.views.sender_intel.build_report", side_effect=RuntimeError("boom")):
            self.client.get(reverse("verify_contact", kwargs={"token": pending.id}))
        mock_send.assert_called_once()
        self.assertIn("sender report failed", mock_send.call_args.kwargs["message"])
        pending.refresh_from_db()
        self.assertIsNotNone(pending.delivered_at)

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


class SenderIntelTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_client_ip_prefers_cloudflare_header(self):
        request = self.factory.get(
            "/", HTTP_CF_CONNECTING_IP="8.8.8.8", HTTP_X_FORWARDED_FOR="1.1.1.1"
        )
        self.assertEqual(sender_intel.client_ip(request), "8.8.8.8")

    def test_client_ip_skips_private_forwarded_hops(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="10.1.2.3, 8.8.8.8, 172.16.0.1")
        self.assertEqual(sender_intel.client_ip(request), "8.8.8.8")

    def test_client_ip_falls_back_to_remote_addr(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="not-an-ip")
        self.assertEqual(sender_intel.client_ip(request), "127.0.0.1")

    def test_parse_user_agent(self):
        cases = {
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0": ("Edge 128", "Windows 10/11", "desktop"),
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36": ("Chrome 127", "Android 14", "phone"),
            "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/604.1": ("Safari 17.5", "iOS 17.5", "tablet"),
            "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0": ("Firefox 130", "Linux", "desktop"),
        }
        for ua, (browser, os_name, device) in cases.items():
            parsed = sender_intel.parse_user_agent(ua)
            self.assertEqual((parsed["browser"], parsed["os"], parsed["device"]), (browser, os_name, device), ua)
            self.assertFalse(parsed["bot"])
        self.assertTrue(sender_intel.parse_user_agent("Mozilla/5.0 (compatible; Googlebot/2.1)")["bot"])
        self.assertTrue(sender_intel.parse_user_agent("python-requests/2.32")["bot"])

    def test_classify_email(self):
        self.assertEqual(sender_intel.classify_email("a@gmail.com")["kind"], "free mail")
        company = sender_intel.classify_email("a+tag@acme-corp.com")
        self.assertEqual(company["kind"], "company/own domain")
        self.assertEqual(company["website"], "https://acme-corp.com")
        self.assertTrue(company["plus_tag"])
        with patch.object(sender_intel, "DISPOSABLE_DOMAINS", frozenset({"mailinator.com"})):
            self.assertEqual(sender_intel.classify_email("x@mailinator.com")["kind"], "disposable")
            self.assertEqual(sender_intel.classify_email("x@sub.mailinator.com")["kind"], "disposable")

    def test_referrer_site_and_humanize(self):
        self.assertEqual(sender_intel.referrer_site("https://www.linkedin.com/in/x/?a=1"), "linkedin.com")
        self.assertEqual(sender_intel.referrer_site(""), "")
        self.assertEqual(sender_intel.humanize_seconds(45), "45s")
        self.assertEqual(sender_intel.humanize_seconds(3725), "1h 2m")
        self.assertEqual(sender_intel.humanize_seconds(None), "unknown")

    def test_geo_lookup_skips_private_addresses(self):
        with patch("main.sender_intel.urllib.request.urlopen") as urlopen:
            self.assertEqual(sender_intel.geo_lookup("127.0.0.1"), {})
            self.assertEqual(sender_intel.geo_lookup("10.0.0.5"), {})
            urlopen.assert_not_called()

    def test_run_lookups_tolerates_failures_and_timeouts(self):
        import time

        with override_settings(SENDER_INTEL_TIMEOUT=0.2):
            results = sender_intel._run_lookups(
                {
                    "ok": lambda: "fine",
                    "boom": lambda: (_ for _ in ()).throw(RuntimeError("x")),
                    "slow": lambda: time.sleep(2) or "late",
                }
            )
        self.assertEqual(results["ok"], "fine")
        self.assertIsNone(results["boom"])
        self.assertIsNone(results["slow"])

    def test_build_report_signals(self):
        pending = PendingContact.objects.create(
            name="Anon", email="throwaway@mailinator.com", subject="Hi", message="Body",
            submitted_ip="8.8.8.8",
            submission_meta={
                "ip": "8.8.8.8",
                "headers": {"user_agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/128.0.0.0 Safari/537.36"},
                "client": {"timezone": "America/Chicago", "dwell": "3"},
                "session": {},
                "at": "2026-09-12T10:00:00+00:00",
            },
        )
        PendingContact.objects.create(
            name="Someone Else", email="other@example.com", subject="Earlier", message="Body",
            submitted_ip="8.8.8.8", submission_meta={"ip": "8.8.8.8"},
        )
        geo = {
            "country": "Netherlands", "regionName": "North Holland", "city": "Amsterdam",
            "lat": 52.37, "lon": 4.89, "timezone": "Europe/Amsterdam",
            "isp": "M247 Europe", "as": "AS9009", "proxy": True, "hosting": True,
        }
        with patch.object(sender_intel, "DISPOSABLE_DOMAINS", frozenset({"mailinator.com"})):
            sections = sender_intel.build_report(
                pending, lookups={"geo_sub": geo, "ptr_sub": "vpn-exit.m247.com", "gravatar": ""}
            )
        report = sender_intel.format_report(sections)
        self.assertIn("Amsterdam, North Holland, Netherlands", report)
        self.assertIn("M247 Europe", report)
        self.assertIn("rDNS vpn-exit.m247.com", report)
        self.assertIn("VPN/proxy", report)
        self.assertIn("America/Chicago disagrees", report)
        self.assertIn("Disposable/throwaway email domain", report)
        self.assertIn("within seconds", report)
        self.assertIn("1 earlier submission(s)", report)
        self.assertIn("Someone Else <other@example.com>", report)
        self.assertIn("https://www.google.com/maps?q=52.37,4.89", report)

    def test_build_report_with_no_metadata_is_quiet(self):
        pending = PendingContact.objects.create(
            name="Plain", email="plain@example.com", subject="Hi", message="Body"
        )
        report = sender_intel.format_report(sender_intel.build_report(pending, lookups={}))
        self.assertIn("IP address  unknown", report)
        self.assertIn("No browser-side fields were posted", report)
