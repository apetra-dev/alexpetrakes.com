"""
Sender intelligence for the contact form.

Collects what a request reveals about the person behind a submission (network
address, browser, locale, how they arrived) and, when a verified message is
delivered, enriches it with best-effort lookups (IP geolocation and ownership,
reverse DNS, email-domain classification, Gravatar) plus a list of signals such
as "VPN in use" or "browser timezone disagrees with IP location".

Every external lookup runs concurrently with a short timeout and degrades to
"unknown" on failure, so a slow or dead third party never blocks delivery.
"""

import hashlib
from datetime import datetime, timezone as dt_timezone
import ipaddress
import json
import logging
import re
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from disposable_email_domains import blocklist as DISPOSABLE_DOMAINS
except ImportError:  # pragma: no cover - the package is in requirements.txt
    DISPOSABLE_DOMAINS = frozenset()

FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com",
        "mac.com", "aol.com", "proton.me", "protonmail.com", "pm.me", "tutanota.com",
        "tuta.io", "tuta.com", "zoho.com", "zohomail.com", "gmx.com", "gmx.net",
        "gmx.de", "mail.com", "yandex.com", "yandex.ru", "fastmail.com", "hey.com",
        "duck.com", "comcast.net", "verizon.net", "att.net", "sbcglobal.net",
        "cox.net", "mail.ru", "qq.com", "163.com", "126.com", "web.de",
    }
)

# Headers that carry the real client address when the app sits behind a proxy.
# Cloudflare sets the first two and a client cannot forge them through it.
# X-Forwarded-For can carry a client-supplied prefix, so the full chain is kept
# in the report and only the first public address is used as "the" IP.
CLIENT_IP_HEADERS = ("HTTP_CF_CONNECTING_IP", "HTTP_TRUE_CLIENT_IP")
FORWARDED_HEADERS = ("HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP")

CAPTURED_HEADERS = {
    "HTTP_USER_AGENT": "user_agent",
    "HTTP_ACCEPT_LANGUAGE": "accept_language",
    "HTTP_REFERER": "referer",
    "HTTP_ORIGIN": "origin",
    "HTTP_SEC_CH_UA": "sec_ch_ua",
    "HTTP_SEC_CH_UA_PLATFORM": "sec_ch_ua_platform",
    "HTTP_SEC_CH_UA_MOBILE": "sec_ch_ua_mobile",
    "HTTP_CF_IPCOUNTRY": "cf_ipcountry",
    "HTTP_X_FORWARDED_FOR": "x_forwarded_for",
    "HTTP_CF_CONNECTING_IP": "cf_connecting_ip",
    "HTTP_TRUE_CLIENT_IP": "true_client_ip",
    "HTTP_DNT": "dnt",
    "HTTP_SEC_GPC": "sec_gpc",
}

# Hidden form fields filled by static/js/main.js (posted as client_<name>).
CLIENT_FIELDS = (
    "timezone",
    "utc_offset",
    "languages",
    "screen",
    "viewport",
    "platform",
    "touch",
    "dwell",
    "color_scheme",
    "loaded_at",
)

# Session keys written by views.home so a submission can say how the visitor
# arrived and how long they had been on the site.
SESSION_KEYS = ("first_seen", "last_seen", "visits", "landing_referer", "landing_path")

BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python-requests|python-urllib|httpclient|"
    r"java/|libwww|scanner|monitor|preview|fetch|headless|phantom|selenium|"
    r"playwright|puppeteer|proofpoint|mimecast|safelinks|urldefense|barracuda",
    re.IGNORECASE,
)

MAX_VALUE_LEN = 500


# --------------------------------------------------------------------------- #
# Capture (runs inside the request, no I/O)
# --------------------------------------------------------------------------- #


def _clean(value, limit=MAX_VALUE_LEN):
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _valid_ip(value):
    try:
        addr = ipaddress.ip_address(value.strip())
    except (ValueError, AttributeError):
        return None
    return str(addr)


def _is_public(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def client_ip(request):
    """Best available client address for a request behind Render/Cloudflare."""
    meta = request.META
    for header in CLIENT_IP_HEADERS:
        ip = _valid_ip(meta.get(header, ""))
        if ip:
            return ip
    for header in FORWARDED_HEADERS:
        for candidate in meta.get(header, "").split(","):
            ip = _valid_ip(candidate)
            if ip and _is_public(ip):
                return ip
    return _valid_ip(meta.get("REMOTE_ADDR", ""))


def request_context(request):
    """Headers worth keeping from a request, keyed by friendly name."""
    return {
        name: _clean(request.META.get(header, ""))
        for header, name in CAPTURED_HEADERS.items()
        if request.META.get(header)
    }


def client_context(post):
    """The hidden client_* fields the page's JavaScript filled in."""
    return {
        field: _clean(post.get(f"client_{field}", ""), 200)
        for field in CLIENT_FIELDS
        if post.get(f"client_{field}")
    }


def session_context(session):
    return {key: session.get(key) for key in SESSION_KEYS if session.get(key) is not None}


def track_visit(request):
    """Record first-seen, landing referrer and visit count on the visitor's session."""
    session = request.session
    now = timezone.now().isoformat(timespec="seconds")
    if "first_seen" not in session:
        session["first_seen"] = now
        session["landing_referer"] = _clean(request.META.get("HTTP_REFERER", ""))
        session["landing_path"] = _clean(request.get_full_path())
    session["visits"] = int(session.get("visits", 0)) + 1
    session["last_seen"] = now


def capture(request):
    """Everything a submission or verification request reveals, as one JSON dict."""
    return {
        "ip": client_ip(request),
        "headers": request_context(request),
        "client": client_context(request.POST) if request.method == "POST" else {},
        "session": session_context(request.session),
        "at": timezone.now().isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- #
# Interpretation (pure functions)
# --------------------------------------------------------------------------- #


def parse_user_agent(ua):
    """Rough browser / OS / device read of a User-Agent string, no dependencies."""
    if not ua:
        return {"browser": "unknown", "os": "unknown", "device": "unknown", "bot": False}

    def version(pattern):
        match = re.search(pattern, ua)
        return match.group(1) if match else ""

    if "Edg/" in ua:
        browser = f"Edge {version(r'Edg/(\d+)')}"
    elif "OPR/" in ua or "Opera" in ua:
        browser = f"Opera {version(r'OPR/(\d+)')}"
    elif "SamsungBrowser/" in ua:
        browser = f"Samsung Internet {version(r'SamsungBrowser/(\d+)')}"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        browser = f"Firefox {version(r'(?:Firefox|FxiOS)/(\d+)')}"
    elif "CriOS/" in ua:
        browser = f"Chrome {version(r'CriOS/(\d+)')} (iOS)"
    elif "Chrome/" in ua or "Chromium/" in ua:
        browser = f"Chrome {version(r'Chrom(?:e|ium)/(\d+)')}"
    elif "Safari/" in ua and "Version/" in ua:
        browser = f"Safari {version(r'Version/(\d+(?:\.\d+)?)')}"
    else:
        browser = ua.split(" ")[0][:40]

    if "Windows NT 10.0" in ua:
        os_name = "Windows 10/11"
    elif "Windows" in ua:
        os_name = f"Windows (NT {version(r'Windows NT ([\d.]+)')})"
    elif "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        os_name = f"iOS {version(r'OS (\d+[_\d]*)').replace('_', '.')}".strip()
    elif "Mac OS X" in ua:
        os_name = f"macOS {version(r'Mac OS X (\d+[_\d]*)').replace('_', '.')}".strip()
    elif "Android" in ua:
        os_name = f"Android {version(r'Android ([\d.]+)')}".strip()
    elif "CrOS" in ua:
        os_name = "ChromeOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "unknown"

    if "iPad" in ua or ("Android" in ua and "Mobile" not in ua):
        device = "tablet"
    elif "Mobile" in ua or "iPhone" in ua:
        device = "phone"
    else:
        device = "desktop"

    return {
        "browser": browser.strip(),
        "os": os_name,
        "device": device,
        "bot": bool(BOT_UA_RE.search(ua)),
    }


def classify_email(email):
    """Domain-level read of an address: disposable, free mail, or a company domain."""
    domain = email.rsplit("@", 1)[-1].lower().strip() if "@" in email else ""
    local = email.rsplit("@", 1)[0] if "@" in email else email
    kind = "unknown"
    if not domain:
        pass
    elif domain in DISPOSABLE_DOMAINS or any(
        domain.endswith("." + d) for d in DISPOSABLE_DOMAINS if "." in d
    ):
        kind = "disposable"
    elif domain in FREE_MAIL_DOMAINS:
        kind = "free mail"
    else:
        kind = "company/own domain"
    return {
        "domain": domain,
        "kind": kind,
        "plus_tag": "+" in local,
        "website": f"https://{domain}" if kind == "company/own domain" else "",
    }


def _parse_iso(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def humanize_seconds(seconds):
    if seconds is None:
        return "unknown"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def referrer_site(url):
    """`https://www.linkedin.com/in/x/?ref=1` -> `linkedin.com`."""
    if not url:
        return ""
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- #
# Enrichment (network, best-effort)
# --------------------------------------------------------------------------- #


def _timeout():
    return float(getattr(settings, "SENDER_INTEL_TIMEOUT", 4))


def geo_lookup(ip):
    """IP geolocation and ownership from the configured provider (ip-api.com by default)."""
    if not ip or not _is_public(ip):
        return {}
    url = getattr(settings, "SENDER_INTEL_GEO_URL", "").format(ip=ip)
    if not url:
        return {}
    request = urllib.request.Request(url, headers={"User-Agent": "alexpetrakes.com contact form"})
    with urllib.request.urlopen(request, timeout=_timeout()) as response:
        data = json.load(response)
    if data.get("status") == "fail":
        logger.info("Geo lookup for %s failed: %s", ip, data.get("message"))
        return {}
    return data


def ptr_lookup(ip):
    """Reverse DNS name for an address (often names the ISP or a corporate network)."""
    if not ip or not _is_public(ip):
        return ""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""


def gravatar_lookup(email):
    """Public Gravatar profile URL for the address, if one exists."""
    if not email:
        return ""
    digest = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    request = urllib.request.Request(
        f"https://www.gravatar.com/avatar/{digest}?d=404", method="HEAD"
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout()):
            return f"https://gravatar.com/{digest}"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ""
        raise


def _run_lookups(jobs):
    """Run {name: callable} concurrently; a job that fails or times out yields None."""
    results = {name: None for name in jobs}
    if not jobs:
        return results
    executor = ThreadPoolExecutor(max_workers=len(jobs))
    futures = {name: executor.submit(fn) for name, fn in jobs.items()}
    # Do not use the executor as a context manager: that joins hung threads.
    executor.shutdown(wait=False)
    for name, future in futures.items():
        try:
            results[name] = future.result(timeout=_timeout() + 0.5)
        except Exception as exc:  # noqa: BLE001 - enrichment must never block delivery
            logger.info("Sender lookup %s failed: %s: %s", name, type(exc).__name__, exc)
    return results


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def _describe_ip(ip, geo, ptr):
    if not ip:
        return "unknown"
    if not _is_public(ip):
        return f"{ip} (private/local address)"
    parts = [ip]
    if geo:
        place = ", ".join(p for p in (geo.get("city"), geo.get("regionName"), geo.get("country")) if p)
        owner = geo.get("isp") or geo.get("org") or geo.get("asname") or ""
        if place:
            parts.append(place)
        if owner:
            parts.append(owner)
        if geo.get("as"):
            parts.append(geo["as"])
    if ptr:
        parts.append(f"rDNS {ptr}")
    return " | ".join(parts)


def _ip_flags(geo):
    if not geo:
        return ""
    flags = []
    if geo.get("proxy"):
        flags.append("VPN/proxy")
    if geo.get("hosting"):
        flags.append("datacenter/hosting")
    if geo.get("mobile"):
        flags.append("mobile carrier")
    return ", ".join(flags) if flags else "residential/business line"


def prior_sightings(pending):
    """Other submissions from the same address or email, oldest first."""
    from .models import PendingContact  # local import: this module is imported by models' users

    ip = pending.submission_meta.get("ip")
    query = PendingContact.objects.exclude(pk=pending.pk).filter(email__iexact=pending.email)
    if ip:
        query = query | PendingContact.objects.exclude(pk=pending.pk).filter(submitted_ip=ip)
    return list(query.order_by("created_at")[:10])


def build_report(pending, lookups=None):
    """
    Assemble the sender-intelligence sections for a delivered message.

    Returns a list of (section_title, [(label, value), ...]). `lookups` lets a
    caller (or test) inject results instead of hitting the network.
    """
    sub = pending.submission_meta or {}
    ver = pending.verification_meta or {}
    sub_ip, ver_ip = sub.get("ip"), ver.get("ip")
    sub_headers, ver_headers = sub.get("headers", {}), ver.get("headers", {})
    client, session = sub.get("client", {}), sub.get("session", {})
    email_info = classify_email(pending.email)

    if lookups is None:
        lookups = {}
        if getattr(settings, "SENDER_INTEL_ENABLED", True):
            jobs = {
                "geo_sub": lambda: geo_lookup(sub_ip),
                "ptr_sub": lambda: ptr_lookup(sub_ip),
                "gravatar": lambda: gravatar_lookup(pending.email),
            }
            if ver_ip and ver_ip != sub_ip:
                jobs["geo_ver"] = lambda: geo_lookup(ver_ip)
                jobs["ptr_ver"] = lambda: ptr_lookup(ver_ip)
            lookups = _run_lookups(jobs)
    geo_sub = lookups.get("geo_sub") or {}
    geo_ver = lookups.get("geo_ver") or ({} if ver_ip != sub_ip else geo_sub)
    ptr_sub = lookups.get("ptr_sub") or ""
    ptr_ver = lookups.get("ptr_ver") or ("" if ver_ip != sub_ip else ptr_sub)
    gravatar = lookups.get("gravatar") or ""

    ua_sub = parse_user_agent(sub_headers.get("user_agent", ""))
    ua_ver = parse_user_agent(ver_headers.get("user_agent", ""))
    signals = []

    # --- Network ---------------------------------------------------------- #
    network = [
        ("IP address", _describe_ip(sub_ip, geo_sub, ptr_sub)),
        ("Connection", _ip_flags(geo_sub) or "unknown"),
    ]
    if geo_sub.get("timezone"):
        network.append(("IP timezone", geo_sub["timezone"]))
    if geo_sub.get("lat") is not None:
        network.append(("Map", f"https://www.google.com/maps?q={geo_sub['lat']},{geo_sub['lon']}"))
    if sub_headers.get("cf_ipcountry"):
        network.append(("Edge country", sub_headers["cf_ipcountry"]))
    if sub_headers.get("x_forwarded_for"):
        network.append(("Forwarded chain", sub_headers["x_forwarded_for"]))
    if geo_sub.get("proxy"):
        signals.append("IP is a known VPN/proxy address; the location above is the exit node, not the person.")
    if geo_sub.get("hosting"):
        signals.append("IP belongs to a hosting/datacenter range (VPN, cloud box, or automation).")

    # --- Device ----------------------------------------------------------- #
    device = [
        ("Browser", f"{ua_sub['browser']} on {ua_sub['os']} ({ua_sub['device']})"),
        ("User agent", sub_headers.get("user_agent", "unknown")),
    ]
    if sub_headers.get("sec_ch_ua_platform"):
        device.append(("Platform hint", sub_headers["sec_ch_ua_platform"].strip('"')))
    if client.get("platform"):
        device.append(("JS platform", client["platform"]))
    if client.get("screen") or client.get("viewport"):
        device.append(("Screen / viewport", f"{client.get('screen', '?')} / {client.get('viewport', '?')}"))
    if client.get("touch"):
        device.append(("Touch points", client["touch"]))
    if client.get("color_scheme"):
        device.append(("Color scheme", client["color_scheme"]))
    if ua_sub["bot"]:
        signals.append("Submission user agent looks automated.")

    # --- Locale ----------------------------------------------------------- #
    locale = []
    if client.get("timezone"):
        tz_line = client["timezone"]
        if client.get("utc_offset"):
            tz_line += f" (UTC offset {client['utc_offset']} min)"
        locale.append(("Browser timezone", tz_line))
        if geo_sub.get("timezone") and geo_sub["timezone"] != client["timezone"]:
            signals.append(
                f"Browser timezone {client['timezone']} disagrees with the IP's timezone "
                f"{geo_sub['timezone']}: VPN, proxy, or travelling. Trust the browser timezone for where they live."
            )
    if client.get("languages"):
        locale.append(("Browser languages", client["languages"]))
    if sub_headers.get("accept_language"):
        locale.append(("Accept-Language", sub_headers["accept_language"]))
    if not client:
        signals.append("No browser-side fields were posted: JavaScript off, a bot, or a scripted POST.")

    # --- Journey ---------------------------------------------------------- #
    journey = []
    first_seen = _parse_iso(session.get("first_seen"))
    submitted_at = _parse_iso(sub.get("at")) or pending.created_at
    landing = session.get("landing_referer", "")
    if landing:
        journey.append(("Arrived from", f"{referrer_site(landing)}  ({landing})"))
    elif session:
        journey.append(("Arrived from", "direct / no referrer (typed URL, bookmark, or a link from an app that strips referrers)"))
    if session.get("landing_path") and session["landing_path"] not in ("/", ""):
        journey.append(("Landing URL", session["landing_path"]))
    if first_seen:
        journey.append(("First visit", first_seen.strftime("%Y-%m-%d %H:%M UTC")))
        journey.append(("Site tenure at submit", humanize_seconds((submitted_at - first_seen).total_seconds())))
    if session.get("visits"):
        journey.append(("Page loads this session", str(session["visits"])))
    if client.get("dwell"):
        journey.append(("Time on page before submit", humanize_seconds(_safe_int(client["dwell"]))))
        if _safe_int(client["dwell"]) is not None and _safe_int(client["dwell"]) < 8:
            signals.append("Form submitted within seconds of the page loading: likely automated or pre-filled.")
    journey.append(("Submitted", submitted_at.strftime("%Y-%m-%d %H:%M:%S UTC")))
    verified_at = _parse_iso(ver.get("at")) or pending.verified_at
    if verified_at:
        journey.append(("Verified", f"{verified_at.strftime('%Y-%m-%d %H:%M:%S UTC')} (after {humanize_seconds((verified_at - submitted_at).total_seconds())})"))
    if ver:
        same_ip = bool(ver_ip) and ver_ip == sub_ip
        same_ua = ver_headers.get("user_agent") == sub_headers.get("user_agent")
        if same_ip and same_ua:
            journey.append(("Verified from", "same address and browser as the submission"))
        else:
            journey.append(("Verified from", _describe_ip(ver_ip, geo_ver, ptr_ver)))
            journey.append(("Verifying browser", f"{ua_ver['browser']} on {ua_ver['os']} ({ua_ver['device']})"))
            if ua_ver["bot"]:
                signals.append("The verification link was opened by something that looks automated (a mail security scanner, most likely). The message may still be legitimate.")
            elif not same_ip:
                signals.append("Verification came from a different address than the submission: another device (phone mail app), a different network, or a forwarded link.")

    # --- Email ------------------------------------------------------------ #
    email_lines = [("Address", pending.email), ("Domain", f"{email_info['domain']} ({email_info['kind']})")]
    if email_info["website"]:
        email_lines.append(("Domain site", email_info["website"]))
    if email_info["plus_tag"]:
        email_lines.append(("Plus-tag", "yes (deliberately distinct alias)"))
    email_lines.append(("Gravatar", gravatar or "none"))
    if email_info["kind"] == "disposable":
        signals.append("Disposable/throwaway email domain. Rely on the network, device and journey sections instead.")
    elif email_info["kind"] == "company/own domain":
        signals.append(f"Address is on its own domain; {email_info['website']} probably identifies the organisation.")

    # --- History ---------------------------------------------------------- #
    history = []
    for prior in prior_sightings(pending):
        prior_ip = (prior.submission_meta or {}).get("ip") or prior.submitted_ip or "?"
        status = "delivered" if prior.delivered_at else ("verified" if prior.verified_at else "never verified")
        history.append(
            (
                prior.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                f"{prior.name} <{prior.email}> from {prior_ip}, subject: {prior.subject[:60]} [{status}]",
            )
        )
    if history:
        signals.append(f"{len(history)} earlier submission(s) from the same address or email (see History).")

    sections = [
        ("Signals", [("", s) for s in signals] or [("", "Nothing unusual.")]),
        ("Network", network),
        ("Device", device),
        ("Locale", locale or [("", "no locale data")]),
        ("Journey", journey),
        ("Email", email_lines),
    ]
    if history:
        sections.append(("History (same address or email)", history))
    return sections


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def format_report(sections):
    """Plain-text rendering of build_report() output for the notification email."""
    lines = []
    for title, rows in sections:
        lines.append(title)
        lines.append("-" * len(title))
        width = max((len(label) for label, _ in rows if label), default=0)
        for label, value in rows:
            if label:
                lines.append(f"{label.ljust(width)}  {value}")
            else:
                lines.append(f"- {value}")
        lines.append("")
    return "\n".join(lines).rstrip()
