from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override as language_override
from .forms import GalleryEntryForm, PhotosField
from .models import Circle, Gallery, GalleryEntry, Glaze, GlazeUse, Ingredient, Invitation, Mold, Photo, Piece, Progress, RecipeVersion, User
from .services import save_photos

def image_file(name='piece.png'):
    buffer = BytesIO()
    Image.new('RGB',(100,80),'#a5683e').save(buffer,'PNG')
    return SimpleUploadedFile(name,buffer.getvalue(),content_type='image/png')

@override_settings(LANGUAGE_CODE='es', ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver', 'canela.example.test'], CSRF_TRUSTED_ORIGINS=['https://canela.example.test'])
class StudioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('ana',password='Una-clave-larga-294!')
        cls.partner = User.objects.create_user('bea',password='Una-clave-distinta-294!')
        cls.stranger = User.objects.create_user('carla',password='Otra-clave-distinta-294!')

    def setUp(self):
        language = language_override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        media_parent = settings.BASE_DIR / 'data'
        media_parent.mkdir(exist_ok=True)
        self.media = TemporaryDirectory(dir=media_parent)
        assert Path(self.media.name).resolve().is_relative_to(media_parent.resolve())
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.client.force_login(self.owner)
        self.piece = Piece.objects.create(owner=self.owner,name='Cuenco',notes='NOTA MUY PRIVADA',clay='Gres')
        self.photo = save_photos([image_file()],piece=self.piece)[0]

    def test_private_piece_and_photos_are_inaccessible_to_other_users(self):
        for user in [self.partner,self.stranger]:
            self.client.force_login(user)
            self.assertNotContains(self.client.get(reverse('pieces')),'Cuenco')
            for name in ['piece','piece_edit','progress_add','glaze_use_add']:
                self.assertEqual(self.client.get(reverse(name,args=[self.piece.pk])).status_code,404)
            self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)
        self.assertEqual(self.client.get('/protected-media/'+self.photo.original.name).status_code,404)

    def test_piece_deletion_requires_owner_confirmation_and_csrf(self):
        url=reverse('piece_delete',args=[self.piece.pk])
        self.assertContains(self.client.get(url),'Eliminar definitivamente')
        self.assertTrue(Piece.objects.filter(pk=self.piece.pk).exists())
        self.assertEqual(self.client.post(url).status_code,400)
        csrf_client=Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(url,{'confirm_delete':'yes'}).status_code,403)
        circle=Circle.objects.create(owner=self.owner,name='Compartido')
        circle.members.add(self.partner)
        self.piece.shared_groups.add(circle)
        for user in [self.partner,self.stranger]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,404)
            self.assertNotContains(self.client.get(reverse('piece',args=[self.piece.pk])),'Eliminar pieza',status_code=200 if user==self.partner else 404)
        self.client.logout()
        self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,302)
        self.assertTrue(Piece.objects.filter(pk=self.piece.pk).exists())

    def test_delete_piece_revokes_gallery_and_photos_but_preserves_inventory(self):
        mold=Mold.objects.create(owner=self.owner,name='Molde conservado')
        glaze=Glaze.objects.create(owner=self.owner,name='Esmalte conservado')
        self.piece.mold=mold
        self.piece.save()
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze)
        event=Progress.objects.create(piece=self.piece,stage='raw')
        event_photo=save_photos([image_file()],piece=self.piece,progress=event)[0]
        other=Piece.objects.create(owner=self.owner,name='Otra pieza')
        other_photo=save_photos([image_file()],piece=other)[0]
        gallery=Gallery.objects.create(owner=self.owner,name='Exposición',audience='public')
        entry=GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Cuenco público')
        entry.photos.add(self.photo,event_photo)
        files=[field for photo in [self.photo,event_photo] for field in [photo.original,photo.image,photo.thumbnail]]
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(reverse('piece_delete',args=[self.piece.pk]),{'confirm_delete':'yes'})
            self.assertTrue(all(field.storage.exists(field.name) for field in files))
        self.assertRedirects(response,reverse('pieces'))
        self.assertFalse(Piece.objects.filter(pk=self.piece.pk).exists())
        self.assertFalse(Progress.objects.filter(pk=event.pk).exists())
        self.assertFalse(GlazeUse.objects.filter(pk=use.pk).exists())
        self.assertFalse(GalleryEntry.objects.filter(pk=entry.pk).exists())
        self.assertFalse(any(field.storage.exists(field.name) for field in files))
        self.assertTrue(other_photo.original.storage.exists(other_photo.original.name))
        self.assertTrue(Mold.objects.filter(pk=mold.pk).exists())
        self.assertTrue(Glaze.objects.filter(pk=glaze.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('gallery',args=[gallery.pk])),'Cuenco público')

    def test_group_sharing_is_read_only_and_revocable(self):
        circle = Circle.objects.create(owner=self.owner,name='Nuestro taller')
        circle.members.add(self.owner,self.partner)
        self.piece.shared_groups.add(circle)
        self.client.force_login(self.partner)
        self.assertContains(self.client.get(reverse('piece',args=[self.piece.pk])),'NOTA MUY PRIVADA')
        response = self.client.get(reverse('photo',args=[self.photo.pk]))
        self.assertEqual(response.status_code,200)
        response.close()
        self.assertEqual(self.client.post(reverse('piece_edit',args=[self.piece.pk]),{'name':'Robada'}).status_code,404)
        circle.members.remove(self.partner)
        self.assertEqual(self.client.get(reverse('piece',args=[self.piece.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)

    def test_public_gallery_only_exposes_selected_fields_and_photos(self):
        private_photo = save_photos([image_file()],piece=self.piece)[0]
        gallery = Gallery.objects.create(owner=self.owner,name='Mi colección',audience='public',notes='NOTAS GALERIA PRIVADAS')
        entry = GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Título público',description='Descripción elegida')
        entry.photos.add(self.photo)
        self.client.logout()
        response = self.client.get(reverse('gallery',args=[gallery.pk]))
        self.assertContains(response,'Título público')
        self.assertNotContains(response,'NOTA MUY PRIVADA')
        self.assertNotContains(response,'NOTAS GALERIA PRIVADAS')
        self.assertNotContains(response,str(private_photo.pk))
        response = self.client.get(reverse('photo',args=[self.photo.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        response.close()
        self.assertEqual(self.client.get(reverse('photo',args=[private_photo.pk])).status_code,404)
        gallery.audience='private'
        gallery.save()
        self.assertEqual(self.client.get(reverse('gallery',args=[gallery.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)

    def test_group_gallery_does_not_open_private_piece(self):
        circle=Circle.objects.create(owner=self.owner,name='Grupo')
        circle.members.add(self.partner,self.owner)
        gallery=Gallery.objects.create(owner=self.owner,name='Compartida',audience='group')
        gallery.shared_groups.add(circle)
        entry=GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Solo mi título')
        entry.photos.add(self.photo)
        self.client.force_login(self.partner)
        self.assertContains(self.client.get(reverse('gallery',args=[gallery.pk])),'Solo mi título')
        self.assertEqual(self.client.get(reverse('piece',args=[self.piece.pk])).status_code,404)
        response = self.client.get(reverse('photo',args=[self.photo.pk]))
        self.assertEqual(response.status_code,200)
        response.close()
        circle.members.remove(self.partner)
        self.assertEqual(self.client.get(reverse('photo',args=[self.photo.pk])).status_code,404)

    def test_forged_gallery_photo_and_piece_are_rejected(self):
        other=Piece.objects.create(owner=self.partner,name='Otra')
        other_photo=save_photos([image_file()],piece=other)[0]
        form=GalleryEntryForm({'piece':self.piece.pk,'title':'Presentación','photos':[other_photo.pk]},user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('photos',form.errors)
        form=GalleryEntryForm({'piece':other.pk,'title':'Presentación'},user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('piece',form.errors)

    def test_recipe_versions_keep_historical_uses(self):
        glaze=Glaze.objects.create(owner=self.owner,name='Avena')
        url=reverse('recipe_add',args=[glaze.pk])
        self.assertEqual(self.client.post(url,{'ingredients':'Feldespato; 40\nSílice; 60'}).status_code,302)
        first=glaze.latest_recipe
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze,recipe_version=first)
        self.client.post(url,{'ingredients':'Feldespato; 45\nSílice; 55'})
        self.assertEqual(glaze.latest_recipe.number,2)
        use.refresh_from_db()
        self.assertEqual(use.recipe_version_id,first.pk)
        self.assertEqual(first.ingredients.get(name='Feldespato').percentage,Decimal('40'))
        invalid=self.client.post(url,{'ingredients':'Feldespato; 45\nSílice; 45'})
        self.assertContains(invalid,'sumar exactamente 100')
        self.assertEqual(glaze.versions.count(),2)

    def test_assign_multiple_glazes_and_keep_application_details(self):
        first=Glaze.objects.create(owner=self.owner,name='Avena')
        second=Glaze.objects.create(owner=self.owner,name='Bruma')
        recipe=RecipeVersion.objects.create(glaze=first,number=1)
        payload={'name':'Con dos esmaltes','stage':'glazed','started_on':'2026-10-25',
                 'glazes_present':'1','glazes':[first.pk,second.pk]}
        self.assertEqual(self.client.post(reverse('piece_new'),payload).status_code,302)
        piece=Piece.objects.get(name='Con dos esmaltes')
        self.assertEqual(piece.glaze_uses.count(),2)
        use=piece.glaze_uses.get(glaze=first)
        self.assertEqual(use.recipe_version_id,recipe.pk)
        self.assertIsNone(use.layers)
        use.grams=Decimal('35')
        use.layers=3
        use.zone='Interior'
        use.save()
        RecipeVersion.objects.create(glaze=first,number=2)
        self.assertEqual(self.client.post(reverse('piece_edit',args=[piece.pk]),payload).status_code,302)
        use.refresh_from_db()
        self.assertEqual(use.grams,Decimal('35'))
        self.assertEqual(use.layers,3)
        self.assertEqual(use.recipe_version_id,recipe.pk)
        payload['glazes']=[first.pk]
        self.client.post(reverse('piece_edit',args=[piece.pk]),payload)
        self.assertEqual(piece.glaze_uses.count(),1)
        self.assertTrue(piece.glaze_uses.filter(pk=use.pk).exists())

    def test_piece_glaze_selection_rejects_foreign_private_glaze(self):
        hidden=Glaze.objects.create(owner=self.partner,name='No disponible')
        response=self.client.post(reverse('piece_new'),{
            'name':'No guardar','stage':'process','started_on':'2026-10-25',
            'glazes_present':'1','glazes':[hidden.pk],
        })
        self.assertEqual(response.status_code,200)
        self.assertFalse(Piece.objects.filter(name='No guardar').exists())
        self.assertFalse(GlazeUse.objects.filter(glaze=hidden).exists())

    def test_unavailable_historical_glaze_is_preserved_and_not_exposed(self):
        hidden=Glaze.objects.create(owner=self.partner,name='RECETA PRIVADA AJENA')
        use=GlazeUse.objects.create(piece=self.piece,glaze=hidden,grams=20)
        response=self.client.get(reverse('piece_edit',args=[self.piece.pk]))
        self.assertNotContains(response,'RECETA PRIVADA AJENA')
        response=self.client.post(reverse('piece_edit',args=[self.piece.pk]),{
            'name':self.piece.name,'stage':'raw','started_on':'2026-10-25','glazes_present':'1',
        })
        self.assertEqual(response.status_code,302)
        self.assertTrue(GlazeUse.objects.filter(pk=use.pk).exists())

    def test_application_edit_preserves_recipe_and_checks_piece_owner(self):
        glaze=Glaze.objects.create(owner=self.owner,name='Avena')
        recipe=RecipeVersion.objects.create(glaze=glaze,number=1)
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze,recipe_version=recipe)
        RecipeVersion.objects.create(glaze=glaze,number=2)
        url=reverse('glaze_use_edit',args=[self.piece.pk,use.pk])
        response=self.client.post(url,{'glaze':glaze.pk,'grams':'24.5','layers':'2','zone':'Exterior','method':'Pincel'})
        self.assertEqual(response.status_code,302)
        use.refresh_from_db()
        self.assertEqual(use.grams,Decimal('24.5'))
        self.assertEqual(use.recipe_version_id,recipe.pk)
        self.client.force_login(self.partner)
        self.assertEqual(self.client.post(url,{'glaze':glaze.pk}).status_code,404)

    def test_piece_owner_and_associations_cannot_be_forged(self):
        foreign=Mold.objects.create(owner=self.partner,name='Ajeno')
        payload={'name':'Nueva','stage':'raw','started_on':'2026-10-24','owner':self.partner.pk,'mold':foreign.pk}
        response=self.client.post(reverse('piece_new'),payload)
        self.assertEqual(response.status_code,200)
        self.assertFalse(Piece.objects.filter(name='Nueva').exists())
        payload.pop('mold')
        response=self.client.post(reverse('piece_new'),payload)
        self.assertEqual(response.status_code,302)
        self.assertEqual(Piece.objects.get(name='Nueva').owner_id,self.owner.pk)

    def test_backdated_progress_does_not_replace_latest_stage(self):
        Progress.objects.create(piece=self.piece,date='2026-10-20',stage='finished')
        self.client.post(reverse('progress_add',args=[self.piece.pk]),{'date':'2026-10-10','stage':'raw','notes':'Primer día'})
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.stage,'finished')

    def test_actual_upload_is_saved_and_served_as_sanitized_jpeg(self):
        response=self.client.post(reverse('progress_add',args=[self.piece.pk]),{'date':'2026-10-24','stage':'raw','notes':'Con fotos','photos':[image_file()]})
        self.assertEqual(response.status_code,302)
        photo=self.piece.photos.order_by('-created_at').first()
        self.assertIsNotNone(photo.progress)
        with photo.image.open('rb') as file:
            normalized=Image.open(file)
            self.assertEqual(normalized.format,'JPEG')
            self.assertFalse(normalized.getexif())

    def test_glaze_reference_photos_follow_resource_permissions(self):
        response=self.client.post(reverse('glaze_new'),{
            'name':'Avena con fotos','kind':'commercial','brand':'Bote de referencia',
            'finish':'Satinado','temperature':'1220–1260 °C','photos':[image_file()],
        })
        self.assertEqual(response.status_code,302)
        glaze=Glaze.objects.get(name='Avena con fotos')
        photo=glaze.photos.get()
        self.assertContains(self.client.get(reverse('glaze',args=[glaze.pk])),str(photo.pk))
        self.assertContains(self.client.get(reverse('glazes')),str(photo.pk))
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(reverse('photo',args=[photo.pk])).status_code,404)
        circle=Circle.objects.create(owner=self.owner,name='Esmaltes compartidos')
        circle.members.add(self.owner,self.partner)
        glaze.group=circle
        glaze.save()
        response=self.client.get(reverse('photo',args=[photo.pk]))
        self.assertEqual(response.status_code,200)
        response.close()
        circle.members.remove(self.partner)
        self.assertEqual(self.client.get(reverse('photo',args=[photo.pk])).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('photo',args=[photo.pk])).status_code,404)

    def test_glaze_edit_adds_photos_without_replacing_existing_ones(self):
        glaze=Glaze.objects.create(owner=self.owner,name='Receta con referencias')
        first=save_photos([image_file()],glaze=glaze)[0]
        response=self.client.post(reverse('glaze_edit',args=[glaze.pk]),{
            'name':glaze.name,'kind':'recipe','photos':[image_file('segunda.png')],
        })
        self.assertEqual(response.status_code,302)
        self.assertEqual(glaze.photos.count(),2)
        self.assertTrue(glaze.photos.filter(pk=first.pk).exists())

    def test_invalid_and_large_files_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            PhotosField().clean([SimpleUploadedFile('bad.svg',b'<svg/>')])
        with self.assertRaises(ValidationError):
            PhotosField().clean([SimpleUploadedFile('large.jpg',b'x'*(5*1024*1024+1))])

    def test_invitation_is_single_use_and_no_open_registration(self):
        circle=Circle.objects.create(owner=self.owner,name='Dos')
        token=Invitation.objects.create(created_by=self.owner,circle=circle,expires_at=timezone.now()+timedelta(days=1))
        self.client.force_login(self.partner)
        self.assertEqual(self.client.post(reverse('accept_invite',args=[token.pk])).status_code,302)
        self.assertTrue(circle.members.filter(pk=self.partner.pk).exists())
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(reverse('accept_invite',args=[token.pk])).status_code,410)
        self.assertFalse(circle.members.filter(pk=self.stranger.pk).exists())
        self.assertEqual(self.client.get(reverse('setup')).status_code,302)

    @override_settings(ALLOW_NEW_ACCOUNTS=True)
    def test_invitation_can_create_a_new_private_account(self):
        token=Invitation.objects.create(created_by=self.owner,expires_at=timezone.now()+timedelta(days=1))
        self.client.logout()
        response=self.client.post(reverse('accept_invite',args=[token.pk]),{
            'username':'nueva','display_name':'Nueva artesana','email':'nueva@example.com',
            'password1':'Una-clave-muy-segura-384!', 'password2':'Una-clave-muy-segura-384!',
        })
        self.assertEqual(response.status_code,302)
        created=User.objects.get(username='nueva')
        self.assertFalse(created.is_staff)
        self.assertNotContains(self.client.get(reverse('pieces')),'Cuenco')
        token.refresh_from_db()
        self.assertEqual(token.used_by_id,created.pk)

    def test_account_email_is_required_valid_and_case_insensitively_unique(self):
        from .forms import AccountForm
        payload={'username':'registro','display_name':'Registro','password1':'Una-clave-muy-segura-384!','password2':'Una-clave-muy-segura-384!'}
        for email in ['', 'no-es-un-correo']:
            form=AccountForm({**payload,'email':email})
            self.assertFalse(form.is_valid())
            self.assertIn('email',form.errors)
        form=AccountForm({**payload,'email':'  Taller@Example.COM  '})
        self.assertTrue(form.is_valid(),form.errors)
        user=form.save()
        self.assertEqual(user.email,'taller@example.com')
        duplicate=AccountForm({**payload,'username':'otro-registro','email':'TALLER@example.com'})
        self.assertFalse(duplicate.is_valid())
        self.assertIn('email',duplicate.errors)

    def test_profile_can_add_email_without_exposing_it_in_pieces_or_galleries(self):
        self.assertContains(self.client.get(reverse('account')),'Correo electrónico')
        response=self.client.post(reverse('account'),{'display_name':'Ana','email':'  Ana@Example.COM  ','bio':'Mi taller'})
        self.assertRedirects(response,reverse('account'))
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email,'ana@example.com')
        self.assertEqual(self.owner.display_name,'Ana')
        self.assertNotContains(self.client.get(reverse('piece',args=[self.piece.pk])),'ana@example.com')
        # Keeping one's own address is valid; another account cannot reuse it.
        self.assertEqual(self.client.post(reverse('account'),{'display_name':'Ana','email':'ANA@example.com','bio':''}).status_code,302)
        self.client.force_login(self.partner)
        response=self.client.post(reverse('account'),{'display_name':'Bea','email':'ana@example.com','bio':''})
        self.assertContains(response,'Ya existe una cuenta con este correo electrónico.')
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.email,'')
        gallery=Gallery.objects.create(owner=self.owner,name='Exposición',audience='public')
        GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Cuenco público')
        self.client.logout()
        self.assertNotContains(self.client.get(reverse('gallery',args=[gallery.pk])),'ana@example.com')

    def test_email_uniqueness_is_enforced_in_database_without_breaking_legacy_accounts(self):
        from django.db import IntegrityError, transaction
        self.owner.email='ana@example.com'
        self.owner.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username='duplicado',email=' ANA@Example.COM ')
        # Existing users without email can still sign in.
        self.client.logout()
        self.assertTrue(self.client.login(username='bea',password='Una-clave-distinta-294!'))

    @override_settings(ALLOW_NEW_ACCOUNTS=False)
    def test_closed_registration_blocks_old_invites_and_new_links(self):
        token=Invitation.objects.create(created_by=self.owner,expires_at=timezone.now()+timedelta(days=1))
        self.assertEqual(self.client.post(reverse('invite')).status_code,403)
        self.assertNotContains(self.client.get(reverse('account')),'Crear una invitación')
        self.client.logout()
        count=User.objects.count()
        url=reverse('accept_invite',args=[token.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post(url,{'username':'nueva','password1':'Una-clave-muy-segura-384!','password2':'Una-clave-muy-segura-384!'}).status_code,403)
        self.assertEqual(User.objects.count(),count)
        token.refresh_from_db()
        self.assertIsNone(token.used_at)
        self.assertTrue(self.client.login(username='ana',password='Una-clave-larga-294!'))

    def test_public_domain_and_https_origin_are_configured(self):
        self.assertIn('canela.example.test',settings.ALLOWED_HOSTS)
        self.assertIn('https://canela.example.test',settings.CSRF_TRUSTED_ORIGINS)
        response=self.client.get(reverse('account'),HTTP_HOST='canela.example.test',secure=True)
        self.assertEqual(response.status_code,200)

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'), SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_login_with_csrf_through_https_proxy(self):
        client=Client(enforce_csrf_checks=True)
        headers={'HTTP_HOST':'canela.example.test','HTTP_X_FORWARDED_PROTO':'https'}
        response=client.get(reverse('login'),**headers)
        self.assertEqual(response.status_code,200)
        self.assertTrue(client.cookies['csrftoken']['secure'])
        response=client.post(reverse('login'),{'username':'ana','password':'Una-clave-larga-294!','csrfmiddlewaretoken':client.cookies['csrftoken'].value},HTTP_ORIGIN='https://canela.example.test',**headers)
        self.assertEqual(response.status_code,302)
        self.assertTrue(client.cookies['sessionid']['secure'])
        self.assertEqual(client.get(reverse('account'),**headers).status_code,200)

    def test_gallery_presentation_can_be_edited_without_changing_private_piece(self):
        gallery=Gallery.objects.create(owner=self.owner,name='Colección')
        entry=GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Antes')
        entry.photos.add(self.photo)
        url=reverse('gallery_entry_edit',args=[gallery.pk,entry.pk])
        response=self.client.get(url)
        self.assertContains(response,'data-gallery-photo-choice')
        self.assertTrue(response.context['photo_choices'][0]['selected'])
        response=self.client.post(url,{'piece':self.piece.pk,'title':'Después','description':'Presentación pública','photos':[self.photo.pk]})
        self.assertRedirects(response,reverse('gallery_manage',args=[gallery.pk]))
        self.assertEqual(gallery.entries.count(),1)
        entry.refresh_from_db()
        self.assertEqual(entry.public_presentation.title,'Después')
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.notes,'NOTA MUY PRIVADA')
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get(reverse('gallery_manage',args=[gallery.pk])).status_code,404)

    def test_gallery_entry_can_be_created_with_explicit_photo_selection(self):
        gallery=Gallery.objects.create(owner=self.owner,name='Galería')
        response=self.client.post(reverse('gallery_entry',args=[gallery.pk]),{
            'piece':self.piece.pk,'title':'Para enseñar','description':'Solo esto',
            'photos':[self.photo.pk],
        })
        self.assertEqual(response.status_code,302)
        entry=gallery.entries.get()
        self.assertEqual(list(entry.public_presentation.photos.all()),[self.photo])
        self.assertEqual(entry.public_presentation.description,'Solo esto')

    def test_csrf_protection_and_post_only_logout(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse('piece_new'),{'name':'Sin CSRF'}).status_code,403)
        self.assertEqual(client.get(reverse('logout')).status_code,405)

    def test_login_is_throttled(self):
        self.client.logout()
        for _ in range(8):
            self.client.post(reverse('login'),{'username':'ana','password':'incorrecta'})
        response=self.client.post(reverse('login'),{'username':'ana','password':'incorrecta'})
        self.assertEqual(response.status_code,429)

    def test_all_primary_pages_render(self):
        mold=Mold.objects.create(owner=self.owner,name='Molde')
        glaze=Glaze.objects.create(owner=self.owner,name='Prueba')
        circle=Circle.objects.create(owner=self.owner,name='Grupo')
        circle.members.add(self.owner)
        gallery=Gallery.objects.create(owner=self.owner,name='Colección')
        urls=[reverse(n) for n in ['dashboard','pieces','piece_new','molds','mold_new','glazes','glaze_new','galleries','gallery_new','circles','circle_new','account','password_change']]
        urls += [reverse(n,args=[pk]) for n,pk in [('piece',self.piece.pk),('piece_edit',self.piece.pk),('progress_add',self.piece.pk),('glaze_use_add',self.piece.pk),('mold',mold.pk),('mold_edit',mold.pk),('glaze',glaze.pk),('glaze_edit',glaze.pk),('recipe_add',glaze.pk),('sample_add',glaze.pk),('circle',circle.pk),('gallery',gallery.pk),('gallery_edit',gallery.pk),('gallery_entry',gallery.pk)]]
        urls += [reverse('gallery_entry',args=[gallery.pk])+'?piece='+str(self.piece.pk),reverse('pieces')+'?stage=raw']
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code,200)

    def test_htmx_filter_and_pagination_preserve_search(self):
        for i in range(19):
            Piece.objects.create(owner=self.owner,name=f'Colección {i}',stage='raw')
        response=self.client.get(reverse('pieces'),{'q':'Colección','stage':'raw'},HTTP_HX_REQUEST='true')
        self.assertContains(response,'piece-results')
        self.assertNotContains(response,'<html')
        self.assertContains(response,'page=2')
        self.assertNotContains(response,'??')
        self.assertContains(response,'stage=raw')

    def test_live_resource_search_respects_visibility_and_mold_state(self):
        circle=Circle.objects.create(owner=self.partner,name='Taller compartido')
        circle.members.add(self.owner)
        for model,name in [(Glaze,'glazes'),(Mold,'molds')]:
            with self.subTest(resource=name):
                own=model.objects.create(owner=self.owner,name='Azul propio')
                shared=model.objects.create(owner=self.partner,name='Azul compartido')
                shared.group=circle;shared.save()
                model.objects.create(owner=self.stranger,name='Azul secreto')
                if model is Mold:
                    shared.state='drying';shared.save()
                response=self.client.get(reverse(name),{'q':'Azul'},HTTP_HX_REQUEST='true')
                self.assertContains(response,'resource-results')
                self.assertContains(response,'Azul propio')
                if model is Glaze:
                    self.assertContains(response,'Azul compartido')
                    personal_response = self.client.get(reverse(name), {'q':'Azul', 'origin':'personal'}, HTTP_HX_REQUEST='true')
                    self.assertContains(personal_response, 'Azul propio')
                    self.assertNotContains(personal_response, 'Azul compartido')
                else:
                    self.assertContains(response,'Azul compartido')
                self.assertNotContains(response,'<html')
                filters={'q':'Azul','scope':'shared'}
                if model is Mold:filters['state']='drying'
                response=self.client.get(reverse(name),filters,HTTP_HX_REQUEST='true')
                self.assertContains(response,'Azul compartido')
                self.assertNotContains(response,'Azul secreto')
                if model is Mold:self.assertNotContains(response,'Azul propio')

    def test_live_resource_pagination_retains_query_and_scope(self):
        for index in range(19):
            Glaze.objects.create(owner=self.owner,name=f'Ensayo {index}')
        response=self.client.get(reverse('glazes'),{'q':'Ensayo','scope':'shared'},HTTP_HX_REQUEST='true')
        self.assertContains(response,'resource-results')
        self.assertContains(response,'page=2')
        self.assertContains(response,'scope=shared')
        self.assertContains(response,'q=Ensayo')

    def test_open_processes_overview_link_matches_owners_unfinished_pieces(self):
        Piece.objects.create(owner=self.owner,name='Esmaltado pendiente',stage='glazed')
        Piece.objects.create(owner=self.owner,name='Terminada del taller',stage='finished')
        Piece.objects.create(owner=self.stranger,name='Proceso ajeno',stage='raw')
        dashboard=self.client.get(reverse('dashboard'))
        self.assertContains(dashboard,reverse('pieces')+'?stage=open')
        self.assertEqual(dashboard.context['open_count'],2)
        response=self.client.get(reverse('pieces'),{'stage':'open'},HTTP_HX_REQUEST='true')
        self.assertContains(response,'Cuenco')
        self.assertContains(response,'Esmaltado pendiente')
        self.assertNotContains(response,'Terminada del taller')
        self.assertNotContains(response,'Proceso ajeno')
        self.assertEqual(response.context['page'].paginator.count,2)
