import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.db import transaction
from readings.admin_forms import SimpleGroupForm

class Command(BaseCommand):
    help = "Configura grupos; contraseña inicial mediante WI_NET_CONSULTA_PASSWORD."
    @transaction.atomic
    def handle(self, *args, **options):
        groups = {}
        for name, enabled in (("Operadores", ["management", "annual", "notifications", "register", "administration"]), ("Consulta", ["annual", "notifications"])):
            group, _ = Group.objects.get_or_create(name=name)
            form = SimpleGroupForm({"name": name, **{key: True for key in enabled}}, instance=group)
            if not form.is_valid():
                raise CommandError(str(form.errors))
            groups[name] = form.save()
        admins = User.objects.filter(is_superuser=True)
        if not admins.exists():
            raise CommandError("No se encontró el administrador existente.")
        for user in admins:
            user.groups.add(groups["Operadores"])
        consulta, created = User.objects.get_or_create(username="Consulta")
        password = os.environ.get("WI_NET_CONSULTA_PASSWORD")
        if created and not password:
            raise CommandError("Falta la contraseña inicial de Consulta.")
        if password:
            consulta.set_password(password)
        consulta.is_active, consulta.is_staff, consulta.is_superuser = True, False, False
        consulta.save()
        consulta.groups.set([groups["Consulta"]])
        consulta.user_permissions.clear()
        self.stdout.write("Grupos configurados, administrador en Operadores y Consulta activa.")
