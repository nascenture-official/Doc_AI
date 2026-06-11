from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
import os

from .models import Document

class DocumentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")

    def test_document_creation(self):
        doc = Document.objects.create(
            user=self.user,
            title="test.pdf",
            file="pdfs/test.pdf",
            file_size=1024,
            page_count=3,
            status="ready"
        )
        self.assertEqual(doc.title, "test.pdf")
        self.assertEqual(str(doc), "test.pdf")
        self.assertEqual(doc.status, "ready")

class DocumentViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="user1", password="password123")
        self.user2 = User.objects.create_user(username="user2", password="password123")
        
        self.doc1 = Document.objects.create(
            user=self.user1,
            title="user1_file.pdf",
            file=SimpleUploadedFile("user1_file.pdf", b"%PDF-1.4...", content_type="application/pdf"),
            file_size=12,
            page_count=1,
            status="ready"
        )

    def test_list_view_requires_login(self):
        response = self.client.get(reverse("documents:list"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_list_view_authenticated(self):
        self.client.login(username="user1", password="password123")
        response = self.client.get(reverse("documents:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user1_file.pdf")
        self.assertNotContains(response, "user2_file.pdf")

    def test_upload_requires_login(self):
        pdf_file = SimpleUploadedFile("new.pdf", b"%PDF-1.4...", content_type="application/pdf")
        response = self.client.post(reverse("documents:upload_ajax"), {"file": pdf_file})
        self.assertEqual(response.status_code, 302)

    @patch('documents.views.async_task')  # Mock django-q's async_task; the view calls it with a string path
    @patch('documents.views.get_pdf_page_count')
    @patch('time.sleep', return_value=None)  # Skip sleep in tests
    def test_upload_success(self, mock_sleep, mock_page_count, mock_async_task):
        mock_page_count.return_value = 5
        self.client.login(username="user1", password="password123")
        
        pdf_file = SimpleUploadedFile("valid.pdf", b"%PDF-1.4...", content_type="application/pdf")
        response = self.client.post(reverse("documents:upload_ajax"), {"file": pdf_file})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["title"], "valid.pdf")
        self.assertEqual(data["page_count"], 5)
        self.assertEqual(data["status"], "processing")
        
        # Verify db state
        doc = Document.objects.get(id=data["id"])
        self.assertEqual(doc.status, "processing")
        self.assertEqual(doc.page_count, 5)

        # Verify dynamic upload path layout (pdfs/<username>/YYYY/MM/<filename>)
        import datetime
        now = datetime.datetime.now()
        expected_prefix = f"pdfs/user1/{now.strftime('%Y/%m')}/"
        self.assertTrue(doc.file.name.startswith(expected_prefix), f"Expected path to start with {expected_prefix}, got {doc.file.name}")

        # The view calls: async_task('documents.tasks.process_uploaded_document', doc.id, task_name=...)
        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args.args[0], 'documents.tasks.process_uploaded_document')
        self.assertEqual(call_args.args[1], doc.id)
        
        # Clean up files created during test
        if doc.file and os.path.exists(doc.file.path):
            os.remove(doc.file.path)

    @patch('documents.views.get_pdf_page_count')
    @patch('time.sleep', return_value=None)
    def test_upload_invalid_type(self, mock_sleep, mock_page_count):
        self.client.login(username="user1", password="password123")
        txt_file = SimpleUploadedFile("invalid.txt", b"some text", content_type="text/plain")
        response = self.client.post(reverse("documents:upload_ajax"), {"file": txt_file})
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Only PDF files are allowed", data["error"])

    @patch('documents.views.get_pdf_page_count')
    @patch('time.sleep', return_value=None)
    def test_upload_size_limit(self, mock_sleep, mock_page_count):
        self.client.login(username="user1", password="password123")
        
        # Mock file size validation by creating a file larger than 20MB
        large_content = b"x" * (20 * 1024 * 1024 + 1)
        pdf_file = SimpleUploadedFile("too_large.pdf", large_content, content_type="application/pdf")
        
        response = self.client.post(reverse("documents:upload_ajax"), {"file": pdf_file})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("File size exceeds", data["error"])

    @patch('documents.views.get_pdf_page_count')
    @patch('time.sleep', return_value=None)
    def test_upload_parse_failure(self, mock_sleep, mock_page_count):
        mock_page_count.return_value = 0 # 0 indicates parsing failed
        self.client.login(username="user1", password="password123")
        
        pdf_file = SimpleUploadedFile("corrupted.pdf", b"corrupted content", content_type="application/pdf")
        response = self.client.post(reverse("documents:upload_ajax"), {"file": pdf_file})
        
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "failed")

        doc = Document.objects.get(id=data["id"])
        self.assertEqual(doc.status, "failed")
        
        if doc.file and os.path.exists(doc.file.path):
            os.remove(doc.file.path)

    def test_delete_requires_login(self):
        response = self.client.post(reverse("documents:delete", args=[self.doc1.id]))
        self.assertEqual(response.status_code, 302)

    def test_delete_own_document(self):
        self.client.login(username="user1", password="password123")
        
        # Check exists before
        self.assertTrue(Document.objects.filter(id=self.doc1.id).exists())
        
        response = self.client.post(reverse("documents:delete", args=[self.doc1.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        
        # Check deleted after
        self.assertFalse(Document.objects.filter(id=self.doc1.id).exists())

    def test_delete_other_user_document(self):
        self.client.login(username="user2", password="password123")
        
        # Should return 404 (or 403, standard get_object_or_404 returns 404)
        response = self.client.post(reverse("documents:delete", args=[self.doc1.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Document.objects.filter(id=self.doc1.id).exists())

    def test_download_requires_login(self):
        response = self.client.get(reverse("documents:download", args=[self.doc1.id]))
        self.assertEqual(response.status_code, 302)

    def test_download_other_user_document(self):
        self.client.login(username="user2", password="password123")
        response = self.client.get(reverse("documents:download", args=[self.doc1.id]))
        self.assertEqual(response.status_code, 404)
