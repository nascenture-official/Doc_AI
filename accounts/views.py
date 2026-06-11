from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from allauth.account.models import EmailAddress
from allauth.account.internal.flows.email_verification import send_verification_email_to_address
from .forms import ProfileUpdateForm
from .models import UserProfile

class ResendVerificationEmailView(View):
    """Handles the /accounts/confirm-email/ page for link-based email verification.

    GET  → show the verification_sent template.
    POST → resend the verification email using the pending email stored in the session.
    """

    template_name = "account/verification_sent.html"

    def get(self, request):
        email = request.session.get("pending_verification_email")
        email_verified = False
        if email:
            email_verified = EmailAddress.objects.filter(
                email__iexact=email, verified=True
            ).exists()
        return render(request, self.template_name, {
            "email_verified": email_verified,
            "pending_email": email,
        })

    def post(self, request):
        email = request.session.get("pending_verification_email")
        if email:
            try:
                address = EmailAddress.objects.get(email__iexact=email, verified=False)
                send_verification_email_to_address(request, address)
                messages.success(request, f"Verification email resent to {email}.")
            except EmailAddress.DoesNotExist:
                messages.error(request, "Could not find an unverified email address. Please sign up again.")
        else:
            messages.error(request, "Session expired. Please sign up again.")
        return redirect(reverse("account_email_verification_sent"))


class DashboardView(LoginRequiredMixin, View):
    """Main dashboard shown after login."""

    login_url = "/accounts/login/"

    def get(self, request):
        from documents.models import Document
        from chat.models import Conversation, Message
        from django.db.models import Sum

        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        
        # 1. Total Documents
        doc_count = Document.objects.filter(user=request.user).count()
        
        # 2. Total Pages Processed
        total_pages = Document.objects.filter(user=request.user, status='ready').aggregate(Sum('page_count'))['page_count__sum'] or 0
        
        # 3. Total Storage Used (formatted)
        total_bytes = Document.objects.filter(user=request.user).aggregate(Sum('file_size'))['file_size__sum'] or 0
        
        size = float(total_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                total_size = f"{size:.1f} {unit}"
                break
            size /= 1024
        else:
            total_size = f"{size:.1f} GB"

        # 4. Conversations & Messages
        convo_count = Conversation.objects.filter(user=request.user).count()
        msg_count = Message.objects.filter(conversation__user=request.user).count()

        # 5. Recent Lists — only fetch fields actually displayed in the dashboard
        recent_docs = Document.objects.filter(user=request.user).order_by('-uploaded_at').only(
            'id', 'title', 'status', 'uploaded_at', 'file_size'
        )[:5]
        recent_chats = Conversation.objects.filter(user=request.user).order_by('-updated_at').only(
            'id', 'title', 'updated_at'
        )[:5]

        context = {
            "profile": profile,
            "page_title": "Dashboard",
            "doc_count": doc_count,
            "total_pages": total_pages,
            "total_size": total_size,
            "convo_count": convo_count,
            "msg_count": msg_count,
            "recent_docs": recent_docs,
            "recent_chats": recent_chats,
        }
        return render(request, "accounts/dashboard.html", context)


class ProfileView(LoginRequiredMixin, View):
    """User profile update page."""

    login_url = "/accounts/login/"

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = ProfileUpdateForm(instance=profile, user=request.user)
        context = {
            "form": form,
            "profile": profile,
            "page_title": "Edit Profile",
        }
        return render(request, "accounts/profile.html", context)

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=profile,
            user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully! 🎉")
            return redirect("profile")
        context = {
            "form": form,
            "profile": profile,
            "page_title": "Edit Profile",
        }
        return render(request, "accounts/profile.html", context)


class RemoveAvatarView(LoginRequiredMixin, View):
    """AJAX-only endpoint: deletes avatar file from disk + clears the DB field.

    Expects a POST request (CSRF required). Returns JSON:
      {"success": true}  or  {"success": false, "error": "..."}
    """

    login_url = "/accounts/login/"

    def post(self, request):
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            return JsonResponse({"success": False, "error": "Profile not found."}, status=404)

        if profile.avatar:
            storage = profile.avatar.storage
            old_name = profile.avatar.name
            # Clear the DB field first so we don't leave a dangling reference
            profile.avatar = None
            profile.save()
            # Delete the actual file with the storage backend
            try:
                storage.delete(old_name)
            except Exception:
                # File deletion failed but DB is already cleared — log and continue
                pass

        return JsonResponse({"success": True})
