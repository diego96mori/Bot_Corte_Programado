from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

def create_interface_user(**kwargs):
    """Explicit permissions for pre-existing tests of the operational screens."""
    user = get_user_model().objects.create_user(**kwargs)
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="readings", codename__in=["access_management", "access_annual", "access_notifications"]))
    return user
