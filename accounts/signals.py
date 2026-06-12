import os
from django.db.models.signals import post_save, pre_save, post_delete
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a UserProfile when a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Keep profile in sync when User is saved (name/email changes only).

    NOTE: We guard against re-saving when the profile itself triggered
    the User save (e.g. from ProfileUpdateForm.save), which would cause
    a second pre_save signal and interfere with avatar deletion.
    """
    if hasattr(instance, "profile") and not getattr(instance, "_profile_saving", False):
        instance.profile.save()


@receiver(post_delete, sender=UserProfile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Deletes file from filesystem when corresponding UserProfile object is deleted."""
    if instance.avatar:
        if os.path.isfile(instance.avatar.path):
            try:
                os.remove(instance.avatar.path)
            except Exception:
                pass


@receiver(pre_save, sender=UserProfile)
def auto_delete_file_on_change(sender, instance, **kwargs):
    """Deletes old file from filesystem when avatar is replaced or cleared.

    Compares file *names* (strings) rather than FieldFile objects to
    avoid subtle equality edge-cases with cleared/empty fields.
    Also removes the now-empty per-user subfolder if nothing is left.
    """
    if not instance.pk:
        return

    try:
        old_profile = UserProfile.objects.get(pk=instance.pk)
    except UserProfile.DoesNotExist:
        return

    old_name = old_profile.avatar.name if old_profile.avatar else None
    new_name = instance.avatar.name if instance.avatar else None

    # Only act when the old file actually existed and is being replaced/cleared
    if old_name and old_name != new_name:
        storage = old_profile.avatar.storage
        try:
            old_path = storage.path(old_name)
            if os.path.isfile(old_path):
                os.remove(old_path)
                # Clean up empty per-user folder (e.g. media/avatars/<username>/)
                parent_dir = os.path.dirname(old_path)
                if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
        except Exception:
            pass
