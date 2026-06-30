from django.test import TestCase
from django.contrib.auth.models import User
from documents.models import Document, Folder
from teams.models import Workspace, WorkspaceMembership, WorkspaceInvitation, DocumentShare
from teams.permissions import (
    get_user_role,
    is_workspace_admin,
    is_workspace_owner,
    visible_documents_for,
    visible_folders_for,
    pending_invitations_for,
    shared_with_me_documents,
    user_can_view_document,
    user_can_edit_document,
    user_can_delete_document,
    user_can_manage_shares,
    user_can_view_folder,
    user_can_edit_folder,
)
from django.core.files.uploadedfile import SimpleUploadedFile


class TeamsPermissionsTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@example.com', password='pw')
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='pw')
        self.member = User.objects.create_user(username='member', email='member@example.com', password='pw')
        self.outsider = User.objects.create_user(username='outsider', email='outsider@example.com', password='pw')

        self.workspace = Workspace.objects.create(name="Test Workspace", slug="test-workspace", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.owner, role=WorkspaceMembership.ROLE_OWNER)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.admin, role=WorkspaceMembership.ROLE_ADMIN)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member, role=WorkspaceMembership.ROLE_MEMBER)

        fake_file = SimpleUploadedFile("test.pdf", b"file_content", content_type="application/pdf")

        self.ws_doc = Document.objects.create(
            title="Workspace Doc",
            user=self.owner,
            workspace=self.workspace,
            file=fake_file,
            file_size=12
        )
        self.ws_folder = Folder.objects.create(
            name="Workspace Folder",
            user=self.owner,
            workspace=self.workspace
        )

        self.personal_doc = Document.objects.create(
            title="Personal Doc",
            user=self.owner,
            file=fake_file,
            file_size=12
        )
        self.personal_folder = Folder.objects.create(
            name="Personal Folder",
            user=self.owner
        )

        # Uploaded by member
        self.member_ws_doc = Document.objects.create(
            title="Member WS Doc",
            user=self.member,
            workspace=self.workspace,
            file=fake_file,
            file_size=12
        )
        self.member_ws_folder = Folder.objects.create(
            name="Member WS Folder",
            user=self.member,
            workspace=self.workspace
        )

    def test_get_user_role(self):
        self.assertEqual(get_user_role(self.owner, self.workspace), WorkspaceMembership.ROLE_OWNER)
        self.assertEqual(get_user_role(self.admin, self.workspace), WorkspaceMembership.ROLE_ADMIN)
        self.assertEqual(get_user_role(self.member, self.workspace), WorkspaceMembership.ROLE_MEMBER)
        self.assertIsNone(get_user_role(self.outsider, self.workspace))

    def test_is_workspace_admin_and_owner(self):
        self.assertTrue(is_workspace_owner(self.owner, self.workspace))
        self.assertFalse(is_workspace_owner(self.admin, self.workspace))

        self.assertTrue(is_workspace_admin(self.owner, self.workspace))
        self.assertTrue(is_workspace_admin(self.admin, self.workspace))
        self.assertFalse(is_workspace_admin(self.member, self.workspace))

    def test_visible_documents_and_folders(self):
        # Personal
        self.assertIn(self.personal_doc, visible_documents_for(self.owner, None))
        self.assertNotIn(self.ws_doc, visible_documents_for(self.owner, None))
        
        self.assertIn(self.personal_folder, visible_folders_for(self.owner, None))
        self.assertNotIn(self.ws_folder, visible_folders_for(self.owner, None))

        # Workspace
        self.assertIn(self.ws_doc, visible_documents_for(self.admin, self.workspace))
        self.assertIn(self.member_ws_doc, visible_documents_for(self.admin, self.workspace))
        self.assertNotIn(self.ws_doc, visible_documents_for(self.outsider, self.workspace))

        self.assertIn(self.ws_folder, visible_folders_for(self.member, self.workspace))
        self.assertNotIn(self.ws_folder, visible_folders_for(self.outsider, self.workspace))

    def test_document_permissions(self):
        # View
        self.assertTrue(user_can_view_document(self.owner, self.ws_doc))
        self.assertTrue(user_can_view_document(self.admin, self.ws_doc))
        self.assertTrue(user_can_view_document(self.member, self.ws_doc))
        self.assertFalse(user_can_view_document(self.outsider, self.ws_doc))

        # Edit
        self.assertTrue(user_can_edit_document(self.owner, self.ws_doc))
        self.assertTrue(user_can_edit_document(self.admin, self.ws_doc))
        self.assertFalse(user_can_edit_document(self.member, self.ws_doc)) # Member didn't upload it

        self.assertTrue(user_can_edit_document(self.member, self.member_ws_doc)) # Member uploaded it

        # Delete
        self.assertTrue(user_can_delete_document(self.owner, self.ws_doc))
        self.assertTrue(user_can_delete_document(self.admin, self.ws_doc))
        self.assertFalse(user_can_delete_document(self.member, self.ws_doc))
        self.assertTrue(user_can_delete_document(self.member, self.member_ws_doc))

        # Manage shares
        self.assertTrue(user_can_manage_shares(self.owner, self.ws_doc))
        self.assertFalse(user_can_manage_shares(self.member, self.ws_doc))

    def test_folder_permissions(self):
        # View
        self.assertTrue(user_can_view_folder(self.owner, self.ws_folder))
        self.assertTrue(user_can_view_folder(self.member, self.ws_folder))
        self.assertFalse(user_can_view_folder(self.outsider, self.ws_folder))

        # Edit/Delete/Rename
        self.assertTrue(user_can_edit_folder(self.owner, self.ws_folder))
        self.assertTrue(user_can_edit_folder(self.admin, self.ws_folder))
        self.assertFalse(user_can_edit_folder(self.member, self.ws_folder)) # Member didn't upload it
        self.assertTrue(user_can_edit_folder(self.member, self.member_ws_folder)) # Member uploaded it

    def test_document_sharing(self):
        # Share personal doc with admin (view only)
        DocumentShare.objects.create(
            document=self.personal_doc,
            shared_with=self.admin,
            permission=DocumentShare.PERMISSION_VIEW,
            shared_by=self.owner
        )

        self.assertTrue(user_can_view_document(self.admin, self.personal_doc))
        self.assertFalse(user_can_edit_document(self.admin, self.personal_doc))
        self.assertFalse(user_can_delete_document(self.admin, self.personal_doc))

        self.assertIn(self.personal_doc, shared_with_me_documents(self.admin))

        # Update to edit
        share = DocumentShare.objects.get(document=self.personal_doc, shared_with=self.admin)
        share.permission = DocumentShare.PERMISSION_EDIT
        share.save()

        self.assertTrue(user_can_edit_document(self.admin, self.personal_doc))
        self.assertFalse(user_can_delete_document(self.admin, self.personal_doc))

    def test_pending_invitations(self):
        invitation = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            email=self.outsider.email,
            role=WorkspaceMembership.ROLE_MEMBER,
            invited_by=self.owner
        )

        invitations = pending_invitations_for(self.outsider)
        self.assertEqual(invitations.count(), 1)
        self.assertEqual(invitations.first(), invitation)

        # Ensure no invitations for other users
        self.assertEqual(pending_invitations_for(self.owner).count(), 0)

        # Accept invitation
        invitation.status = WorkspaceInvitation.STATUS_ACCEPTED
        invitation.save()

        self.assertEqual(pending_invitations_for(self.outsider).count(), 0)
