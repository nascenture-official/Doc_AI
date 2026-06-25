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


class Folder(models.Model):
    """
    A named folder that can be nested arbitrarily deep.
    parent=None  →  root-level folder.
    Deleting a folder cascades to delete all descendant folders;
    documents inside are orphaned (folder set to NULL) — never deleted.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='folders')
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,   # child folders deleted when parent is deleted
        related_name='children'
    )
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        # Same name allowed inside different parent folders, but not within the same parent
        unique_together = ('user', 'name', 'parent')

    def __str__(self):
        return self.name

    @property
    def document_count(self):
        """Number of documents directly inside this folder (non-recursive)."""
        return self.documents.count()

    def get_ancestors(self):
        """
        Returns an ordered list of ancestor Folder objects from the root
        down to (but not including) this folder.
        """
        ancestors = []
        node = self.parent
        while node is not None:
            ancestors.insert(0, node)
            node = node.parent
        return ancestors

    def get_breadcrumb(self):
        """Full path including self — used for breadcrumb rendering."""
        return self.get_ancestors() + [self]

    def is_ancestor_of(self, other):
        """
        Returns True if self is an ancestor of `other`.
        Used to prevent moving a folder into one of its own descendants.
        """
        node = other.parent
        while node is not None:
            if node.pk == self.pk:
                return True
            node = node.parent
        return False


class Document(models.Model):
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    folder = models.ForeignKey(
        Folder,
        null=True, blank=True,
        on_delete=models.SET_NULL,   # documents survive folder deletion
        related_name='documents'
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    file_size = models.PositiveBigIntegerField()  # In bytes
    page_count = models.PositiveIntegerField(default=0)
    status = models.CharField(choices=STATUS_CHOICES, default='uploading', max_length=20)
    error_message = models.TextField(blank=True, null=True)
    summary_short = models.TextField(blank=True, null=True)
    summary_long = models.TextField(blank=True, null=True)
    rewrite_content = models.TextField(blank=True, null=True)
    rewrite_style = models.CharField(max_length=50, blank=True, null=True)
    key_points = models.TextField(blank=True, null=True)
    faqs = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title

TRANSLATION_LANGUAGES = [
    ('en', 'English'),
    ('hi', 'Hindi'),
]

class DocumentTranslation(models.Model):
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='translations')
    language = models.CharField(max_length=10, choices=TRANSLATION_LANGUAGES)
    translated_text = models.TextField(blank=True, null=True)
    status = models.CharField(choices=STATUS_CHOICES, default='processing', max_length=20)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('document', 'language')

    def __str__(self):
        return f"{self.document.title} - {self.get_language_display()}"

class DocumentComparison(models.Model):
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_comparisons')
    document_base = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comparisons_as_base')
    document_compare = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comparisons_as_compare')
    diff_data = models.TextField(blank=True, null=True)
    ai_summary = models.TextField(blank=True, null=True)
    status = models.CharField(choices=STATUS_CHOICES, default='processing', max_length=20)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'document_base', 'document_compare']

    def __str__(self):
        return f"Comparison: {self.document_base.title} vs {self.document_compare.title}"


class Bookmark(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='bookmarks')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    page_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['page_number']
        unique_together = ('document', 'user', 'page_number')

    def __str__(self):
        return f"Bookmark: {self.document.title} - Page {self.page_number}"


class Highlight(models.Model):
    COLOR_CHOICES = [
        ('yellow', 'Yellow'),
        ('green', 'Green'),
        ('pink', 'Pink'),
        ('blue', 'Blue'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='highlights')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    page_number = models.PositiveIntegerField()
    text = models.TextField()
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default='yellow')
    position_data = models.JSONField(help_text='Schema: {"rects": [{"x1": float, "y1": float, "x2": float, "y2": float, "page": int}], "selected_text": str}')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page_number', 'created_at']

    def __str__(self):
        return f"Highlight on {self.document.title} - Page {self.page_number}"


class Note(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    page_number = models.PositiveIntegerField()
    content = models.TextField()
    highlight = models.OneToOneField(Highlight, on_delete=models.SET_NULL, null=True, blank=True, related_name='note')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page_number', 'created_at']

    def __str__(self):
        return f"Note on {self.document.title} - Page {self.page_number}"
