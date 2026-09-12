import uuid

from django.db import models


class PendingContact(models.Model):
    """
    A contact-form submission. Created when the form is posted, verified when the
    sender clicks the emailed link, delivered when the notification reaches the
    site owner. Records are kept after delivery so repeat senders can be matched
    by address or email in later notifications.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # What the submitting request revealed: ip, headers, JS client fields, session.
    submitted_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    submission_meta = models.JSONField(default=dict, blank=True)

    # Same for the request that opened the verification link.
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_ip = models.GenericIPAddressField(null=True, blank=True)
    verification_meta = models.JSONField(default=dict, blank=True)

    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PendingContact({self.name}, {self.email}, {self.created_at})"

    @property
    def status(self):
        if self.delivered_at:
            return "delivered"
        if self.verified_at:
            return "verified"
        return "pending"
