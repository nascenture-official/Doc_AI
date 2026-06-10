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
    """Keep profile in sync when User is saved."""
    if hasattr(instance, "profile"):
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
    """Deletes old file from filesystem when corresponding UserProfile object is updated with new file or cleared."""
    if not instance.pk:
        return False

    try:
        old_profile = UserProfile.objects.get(pk=instance.pk)
    except UserProfile.DoesNotExist:
        return False

    old_file = old_profile.avatar
    new_file = instance.avatar
    if old_file and old_file != new_file:
        if os.path.isfile(old_file.path):
            try:
                os.remove(old_file.path)
            except Exception:
                pass
