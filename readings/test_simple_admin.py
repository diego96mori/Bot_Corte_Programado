from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.test import TestCase
from django.urls import reverse
from readings.admin_forms import SimpleGroupForm
from readings.models import Node, Reading, ReadingSchedule, ReminderLog

class SimpleAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('administrator', password='test-pass')
        self.client.force_login(self.admin)
        self.node = Node.objects.create(code='SUM-123', name='Prueba', supply_number='123', reading_day=11)
        self.schedule = ReadingSchedule.objects.create(node=self.node, due_date=date(2026,8,11), notes='Lectura mensual', status='COMPLETED')
        self.reading = Reading.objects.create(schedule=self.schedule, reading_date=date(2026,8,11), status='CONFIRMED', confirmed_value=100)

    def test_group_permissions_consulta_and_direct_urls(self):
        form = SimpleGroupForm({'name':'Consulta','annual':True,'notifications':True})
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        user = User.objects.create_user('Consulta', password='test-pass')
        user.groups.add(group)
        self.client.force_login(user)
        self.assertRedirects(self.client.get('/'), reverse('readings:annual_grid'))
        self.assertEqual(self.client.get(reverse('readings:web_reading')).status_code,403)
        self.assertEqual(self.client.post(reverse('readings:web_reading'),{}).status_code,403)
        self.assertEqual(self.client.get(reverse('readings:calendar_events')).status_code,200)
        self.assertEqual(self.client.get('/admin/').status_code,302)
        response = self.client.get(reverse('readings:annual_grid'))
        self.assertNotContains(response,'>GESTIÓN DE LECTURAS</a>')
        self.assertNotContains(response,'data-add-reading>Agregar lectura</button>')

    def test_group_form_and_user_form_render_simple_fields(self):
        response = self.client.get(reverse('admin:auth_group_add'))
        self.assertContains(response,'Ver Gestión de lecturas')
        self.assertNotContains(response,'id_permissions')
        self.assertEqual(self.client.get(reverse('admin:auth_user_add')).status_code,200)
        self.assertEqual(self.client.get(reverse('admin:auth_user_change',args=[self.admin.pk])).status_code,200)

    def test_groups_are_checkboxes_and_node_code_is_visible(self):
        group = Group.objects.create(name='Consulta')
        self.admin.groups.add(group)
        response = self.client.get(reverse('admin:auth_user_change',args=[self.admin.pk]))
        self.assertContains(response, 'type="checkbox" name="groups"')
        self.assertContains(response, f'value="{group.pk}"')
        self.assertContains(self.client.get(reverse('admin:auth_user_add')), 'type="checkbox" name="groups"')
        self.assertContains(self.client.get(reverse('admin:readings_node_changelist')), 'SUM-123')

    def test_cancelled_monthly_and_followup_are_gray(self):
        self.reading.delete()
        self.schedule.status='CANCELLED'
        self.schedule.save()
        ReadingSchedule.objects.create(node=self.node,due_date=date(2026,8,21),notes='Seguimiento de 10 días',status='CANCELLED')
        with patch('django.utils.timezone.localdate',return_value=date(2026,8,11)):
            events=self.client.get(reverse('readings:calendar_events'),{'year':2026,'month':8}).json()['events']
        self.assertEqual(len(events),2)
        self.assertTrue(all(e['state']=='closed' and 'anulada' in e['status_label'] for e in events))

    def test_delete_monthly_cancels_pending_followup_but_keeps_visible(self):
        follow=ReadingSchedule.objects.create(node=self.node,due_date=date(2026,8,21),notes='Seguimiento de 10 días')
        self.client.post(reverse('admin:readings_reading_delete',args=[self.reading.pk]),{'post':'yes'})
        follow.refresh_from_db()
        self.assertEqual(follow.status,'CANCELLED')
        events=self.client.get(reverse('readings:calendar_events'),{'year':2026,'month':8}).json()['events']
        event=next(e for e in events if e['date']=='2026-08-21')
        self.assertEqual(event['state'],'closed')
        self.assertIn('mensual eliminada',event['status_label'])

    def test_user_group_assignment_controls_admin_and_register_is_independent(self):
        form = SimpleGroupForm({'name':'Administrar sin registrar','administration':True,'annual':True})
        self.assertTrue(form.is_valid())
        group = form.save()
        user = User.objects.create_user('operador_nuevo', password='test-pass')
        response = self.client.post(reverse('admin:auth_user_change',args=[user.pk]),{
            'username':user.username,'first_name':'','last_name':'','email':'','is_active':'on','groups':[group.pk],'_save':'Guardar',
        })
        self.assertEqual(response.status_code,302)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm('readings.access_admin'))
        self.assertFalse(user.has_perm('readings.add_reading'))
        self.client.force_login(user)
        self.assertEqual(self.client.get('/admin/').status_code,200)

    def test_reading_only_value_and_photo_editable_and_no_bulk_actions(self):
        url = reverse('admin:readings_reading_change',args=[self.reading.pk])
        response = self.client.post(url, {'confirmed_value':'105,9','schedule':999,'reading_date':'2026-09-01','status':'CANCELLED','_save':'Guardar'})
        self.assertEqual(response.status_code,302)
        self.reading.refresh_from_db()
        self.assertEqual(str(self.reading.confirmed_value),'105.900')
        self.assertEqual(self.reading.reading_date,date(2026,8,11))
        self.assertEqual(self.reading.status,'CONFIRMED')
        listing = self.client.get(reverse('admin:readings_reading_changelist'))
        self.assertNotContains(listing,'name="action"')
        self.assertContains(listing,'Eliminar')
        self.assertEqual(self.client.get(reverse('admin:readings_reading_add')).status_code,403)

    def test_delete_reading_reopens_schedule_but_closed_cycle_stays_gray(self):
        response = self.client.post(reverse('admin:readings_reading_delete',args=[self.reading.pk]),{'post':'yes'})
        self.assertEqual(response.status_code,302)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status,'PENDING')
        self.assertFalse(Reading.objects.filter(pk=self.reading.pk).exists())
        with patch('django.utils.timezone.localdate',return_value=date(2026,9,11)):
            payload = self.client.get(reverse('readings:calendar_events'),{'year':2026,'month':8}).json()
        self.assertTrue(any(e['state']=='closed' for e in payload['events']))
        self.assertFalse(any(e['state']=='completed' for e in payload['events']))

    def test_nodes_default_code_chat_no_delete_and_inactive_hidden(self):
        response = self.client.post(reverse('admin:readings_node_add'),{'name':'Nuevo','location':'Lima','supply_number':'987','provider':'PLUZ','reading_day':2,'active':'on','_save':'Guardar'})
        self.assertEqual(response.status_code,302, response.context and response.context.get('errors'))
        node = Node.objects.get(supply_number='987')
        self.assertEqual(node.code,'SUM-987')
        self.assertEqual(node.telegram_chat_id,8463146362)
        self.assertEqual(self.client.get(reverse('admin:readings_node_delete',args=[node.pk])).status_code,403)
        node.active=False
        node.save()
        self.assertNotContains(self.client.get(reverse('readings:annual_grid')), '>Nuevo<')
        self.assertNotIn(node.pk,[n['id'] for n in self.client.get(reverse('readings:web_reading')).json()['nodes']])

    def test_schedule_state_only_and_reminders_readonly(self):
        response = self.client.post(reverse('admin:readings_readingschedule_change',args=[self.schedule.pk]),{'status':'CANCELLED','_save':'Guardar'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Tiene una lectura confirmada')
        log = ReminderLog.objects.create(schedule=self.schedule,sent_on=date(2026,8,11),chat_id=1)
        self.assertEqual(self.client.get(reverse('admin:readings_reminderlog_add')).status_code,403)
        self.assertEqual(self.client.post(reverse('admin:readings_reminderlog_change',args=[log.pk]),{}).status_code,403)
        self.assertEqual(self.client.get(reverse('admin:readings_reminderlog_delete',args=[log.pk])).status_code,403)
