from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

def document_upload_path(instance, filename):
    """
    Upload documents to: media/pdfs/<username>/%Y/%m/<filename>
    Falls back to user ID if username is somehow unavailable.
    """
    username = instance.user.username or str(instance.user.id)
    now = timezone.now()
    date_path = now.strftime('%Y/%m')
    return f"pdfs/{username}/{date_path}/{filename}"

class Document(models.Model):
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    file_size = models.PositiveBigIntegerField()  # In bytes
    page_count = models.PositiveIntegerField(default=0)
    status = models.CharField(choices=STATUS_CHOICES, default='uploading', max_length=20)
    error_message = models.TextField(blank=True, null=True)
    summary_short = models.TextField(blank=True, null=True)
    summary_long = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title
