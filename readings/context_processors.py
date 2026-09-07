from .services.notifications import get_reading_notifications


def notifications(request):
    if not request.user.is_authenticated or not request.user.has_perm("readings.access_notifications"):
        return {"web_notifications": [], "web_notification_count": 0}
    items = get_reading_notifications()
    return {"web_notifications": items, "web_notification_count": len(items)}
