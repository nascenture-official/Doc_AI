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

    @patch('documents.tasks.process_uploaded_document.delay')  # Mock Celery's .delay() so the task doesn't actually run
    @patch('documents.views.get_pdf_page_count')
    @patch('time.sleep', return_value=None)  # Skip sleep in tests
    def test_upload_success(self, mock_sleep, mock_page_count, mock_delay):
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

        # The view calls: process_uploaded_document.delay(doc.id)
        mock_delay.assert_called_once_with(doc.id)
        
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
        
        # Mock file size validation by creating a file larger than 50MB
        large_content = b"x" * (50 * 1024 * 1024 + 1)
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


# ─── Folder Model Tests ────────────────────────────────────────────────────────

from .models import Folder  # noqa: E402


class FolderModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="folderuser", password="pass")

    def test_create_root_folder(self):
        f = Folder.objects.create(user=self.user, name="Root")
        self.assertIsNone(f.parent)
        self.assertEqual(str(f), "Root")

    def test_create_nested_folder(self):
        root = Folder.objects.create(user=self.user, name="Root")
        child = Folder.objects.create(user=self.user, name="Child", parent=root)
        self.assertEqual(child.parent, root)

    def test_get_ancestors_flat(self):
        root = Folder.objects.create(user=self.user, name="Root")
        child = Folder.objects.create(user=self.user, name="Child", parent=root)
        self.assertEqual(child.get_ancestors(), [root])

    def test_get_ancestors_deep(self):
        a = Folder.objects.create(user=self.user, name="A")
        b = Folder.objects.create(user=self.user, name="B", parent=a)
        c = Folder.objects.create(user=self.user, name="C", parent=b)
        self.assertEqual(c.get_ancestors(), [a, b])

    def test_get_breadcrumb(self):
        a = Folder.objects.create(user=self.user, name="A")
        b = Folder.objects.create(user=self.user, name="B", parent=a)
        self.assertEqual(b.get_breadcrumb(), [a, b])

    def test_is_ancestor_of(self):
        a = Folder.objects.create(user=self.user, name="A")
        b = Folder.objects.create(user=self.user, name="B", parent=a)
        c = Folder.objects.create(user=self.user, name="C", parent=b)
        self.assertTrue(a.is_ancestor_of(c))
        self.assertTrue(b.is_ancestor_of(c))
        self.assertFalse(c.is_ancestor_of(a))

    def test_document_count_property(self):
        folder = Folder.objects.create(user=self.user, name="Docs")
        Document.objects.create(
            user=self.user, folder=folder,
            title="d.pdf", file="pdfs/d.pdf", file_size=10
        )
        self.assertEqual(folder.document_count, 1)


# ─── Folder Views Tests ────────────────────────────────────────────────────────

class FolderViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="fvu1", password="pass")
        self.user2 = User.objects.create_user(username="fvu2", password="pass")
        self.root = Folder.objects.create(user=self.user1, name="Root")
        self.child = Folder.objects.create(user=self.user1, name="Child", parent=self.root)

    def test_create_folder_requires_login(self):
        response = self.client.post(reverse("documents:folder_create"), {"name": "X"})
        self.assertEqual(response.status_code, 302)

    def test_create_root_folder_ajax(self):
        self.client.login(username="fvu1", password="pass")
        response = self.client.post(reverse("documents:folder_create"), {"name": "NewRoot"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["name"], "NewRoot")
        self.assertIsNone(data["parent_id"])

    def test_create_subfolder_ajax(self):
        self.client.login(username="fvu1", password="pass")
        response = self.client.post(
            reverse("documents:folder_create"),
            {"name": "Sub", "parent_id": self.root.pk}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["parent_id"], self.root.pk)

    def test_rename_folder_ajax(self):
        self.client.login(username="fvu1", password="pass")
        response = self.client.post(
            reverse("documents:folder_rename", args=[self.root.pk]),
            {"name": "Renamed"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["name"], "Renamed")
        self.root.refresh_from_db()
        self.assertEqual(self.root.name, "Renamed")

    def test_delete_folder_cascades_children(self):
        self.client.login(username="fvu1", password="pass")
        child_pk = self.child.pk
        response = self.client.post(reverse("documents:folder_delete", args=[self.root.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(Folder.objects.filter(pk=self.root.pk).exists())
        self.assertFalse(Folder.objects.filter(pk=child_pk).exists())

    def test_delete_folder_orphans_documents(self):
        doc = Document.objects.create(
            user=self.user1, folder=self.root,
            title="d.pdf", file="pdfs/d.pdf", file_size=10
        )
        self.client.login(username="fvu1", password="pass")
        self.client.post(reverse("documents:folder_delete", args=[self.root.pk]))
        doc.refresh_from_db()
        self.assertIsNone(doc.folder)

    def test_move_folder_to_new_parent(self):
        other = Folder.objects.create(user=self.user1, name="Other")
        self.client.login(username="fvu1", password="pass")
        response = self.client.post(
            reverse("documents:folder_move", args=[self.root.pk]),
            {"new_parent_id": other.pk}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.root.refresh_from_db()
        self.assertEqual(self.root.parent, other)

    def test_move_folder_into_own_descendant_rejected(self):
        """Critical guard: moving root into child must fail."""
        self.client.login(username="fvu1", password="pass")
        response = self.client.post(
            reverse("documents:folder_move", args=[self.root.pk]),
            {"new_parent_id": self.child.pk}
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Cannot move", data["error"])

    def test_cross_user_folder_access_rejected(self):
        self.client.login(username="fvu2", password="pass")
        # user2 cannot delete user1's folder
        response = self.client.post(reverse("documents:folder_delete", args=[self.root.pk]))
        self.assertEqual(response.status_code, 404)


# ─── Move Document Tests ───────────────────────────────────────────────────────

class MoveDocumentTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username="mdu1", password="pass")
        self.user2 = User.objects.create_user(username="mdu2", password="pass")
        self.folder_a = Folder.objects.create(user=self.user1, name="A")
        self.folder_b = Folder.objects.create(user=self.user1, name="B")
        self.doc = Document.objects.create(
            user=self.user1, title="doc.pdf",
            file="pdfs/doc.pdf", file_size=10
        )

    def test_move_doc_to_folder(self):
        self.client.login(username="mdu1", password="pass")
        response = self.client.post(
            reverse("documents:document_move", args=[self.doc.pk]),
            {"folder_id": self.folder_a.pk}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.folder, self.folder_a)

    def test_move_doc_between_folders(self):
        self.doc.folder = self.folder_a
        self.doc.save()
        self.client.login(username="mdu1", password="pass")
        self.client.post(
            reverse("documents:document_move", args=[self.doc.pk]),
            {"folder_id": self.folder_b.pk}
        )
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.folder, self.folder_b)

    def test_move_doc_to_root(self):
        self.doc.folder = self.folder_a
        self.doc.save()
        self.client.login(username="mdu1", password="pass")
        response = self.client.post(
            reverse("documents:document_move", args=[self.doc.pk]),
            {"folder_id": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.folder)

    def test_move_doc_to_other_user_folder_rejected(self):
        other_folder = Folder.objects.create(user=self.user2, name="OtherUserFolder")
        self.client.login(username="mdu1", password="pass")
        response = self.client.post(
            reverse("documents:document_move", args=[self.doc.pk]),
            {"folder_id": other_folder.pk}
        )
        self.assertEqual(response.status_code, 404)
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.folder)

