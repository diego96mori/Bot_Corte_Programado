from functools import wraps
from django.http import HttpResponseForbidden


def interface_required(permission):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.has_perm("readings." + permission):
                return HttpResponseForbidden("Tu grupo no tiene acceso a esta pantalla.")
            return view(request, *args, **kwargs)
        return wrapped
    return decorate
