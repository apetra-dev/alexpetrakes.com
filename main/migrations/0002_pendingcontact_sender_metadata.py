from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pendingcontact",
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="submitted_ip",
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="submission_meta",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="verified_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="verification_meta",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="pendingcontact",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
