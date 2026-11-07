from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override as language_override
from .models import User, Piece, Mold, Glaze, Sample, Circle, Photo, Progress, Gallery, GalleryEntry, GlazeUse, RecipeVersion
from .services import save_photos
from .tests import image_file


@override_settings(LANGUAGE_CODE='es')
class PhotoHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_user('owner')
        cls.partner=User.objects.create_user('partner')

    def setUp(self):
        language = language_override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.media=TemporaryDirectory(dir=settings.BASE_DIR/'data')
        assert Path(self.media.name).resolve().is_relative_to((settings.BASE_DIR/'data').resolve())
        override=override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)
        self.piece=Piece.objects.create(owner=self.owner,name='Cuenco')
        self.photos=save_photos([image_file('one.png'),image_file('two.png'),image_file('three.png')],piece=self.piece)
        self.manage=reverse('photos_manage',kwargs={'kind':'piece','pk':self.piece.pk})

    def order(self):
        return list(self.piece.photos.values_list('pk',flat=True))

    def test_cover_order_and_appending_keep_a_stable_explicit_order(self):
        ids=[p.pk for p in self.photos]
        self.assertEqual(self.order(),ids)
        self.assertContains(self.client.get(self.manage),'Guardar orden y portada')
        self.assertEqual(self.order(),ids)
        response=self.client.post(self.manage,{'order':ids,'cover':ids[2]})
        self.assertRedirects(response,self.manage)
        self.assertEqual(self.order(),[ids[2],ids[0],ids[1]])
        self.assertEqual(self.piece.cover.pk,ids[2])
        added=save_photos([image_file()],piece=self.piece)[0]
        self.assertEqual(self.order(),[ids[2],ids[0],ids[1],added.pk])
        response=self.client.post(self.manage,{'order':[added.pk,ids[1],ids[0],ids[2]],'save_order':'1'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.piece.cover.pk,added.pk)

    def test_foreign_duplicate_missing_and_stale_photo_ids_cannot_be_ordered(self):
        other=Piece.objects.create(owner=self.owner,name='Otro')
        foreign=save_photos([image_file()],piece=other)[0]
        ids=self.order()
        for order in [[ids[0],ids[0],ids[1]],[foreign.pk,ids[1],ids[2]],ids[:2],['malformed']]:
            self.assertEqual(self.client.post(self.manage,{'order':order,'save_order':'1'}).status_code,400)
            self.assertEqual(self.order(),ids)
        self.assertEqual(self.client.post(self.manage,{'order':ids,'cover':foreign.pk}).status_code,400)

    def test_photo_mutations_are_owner_only_and_require_csrf(self):
        circle=Circle.objects.create(owner=self.owner,name='Taller')
        circle.members.add(self.partner)
        self.piece.shared_groups.add(circle)
        delete=reverse('photo_delete',args=[self.photos[0].pk])
        self.client.force_login(self.partner)
        for url,data in [(self.manage,{'order':self.order(),'save_order':'1'}),(delete,{'confirm_delete':'yes'})]:
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.post(url,data).status_code,404)
        response=self.client.get(reverse('piece',args=[self.piece.pk]))
        self.assertNotContains(response,'Gestionar fotos')
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(delete,{'confirm_delete':'yes'}).status_code,403)
        self.assertEqual(csrf.post(self.manage,{'order':self.order(),'save_order':'1'}).status_code,403)

    def test_delete_photo_removes_only_selected_file_and_revokes_public_access(self):
        photo=self.photos[0]
        fields=[photo.original,photo.image,photo.thumbnail]
        gallery=Gallery.objects.create(owner=self.owner,name='Pública',audience='public')
        entry=GalleryEntry.objects.create(gallery=gallery,piece=self.piece,title='Cuenco')
        entry.photos.add(photo,self.photos[1])
        url=reverse('photo_delete',args=[photo.pk])
        self.assertContains(self.client.get(url),'galerías')
        self.assertEqual(self.client.post(url).status_code,400)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,302)
            self.assertTrue(all(f.storage.exists(f.name) for f in fields))
        self.assertFalse(any(f.storage.exists(f.name) for f in fields))
        self.assertTrue(self.photos[1].image.storage.exists(self.photos[1].image.name))
        self.assertEqual(list(entry.photos.values_list('pk',flat=True)),[self.photos[1].pk])
        self.assertEqual(self.piece.cover.pk,self.photos[1].pk)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('photo',args=[photo.pk])).status_code,404)
        response=self.client.get(reverse('gallery',args=[gallery.pk]))
        self.assertNotContains(response,str(self.photos[2].pk))

    def test_collection_uploads_and_controls_cover_molds_glazes_and_samples(self):
        mold=Mold.objects.create(owner=self.owner,name='Molde')
        glaze=Glaze.objects.create(owner=self.owner,name='Esmalte')
        sample=Sample.objects.create(glaze=glaze,clay='Gres',temperature=1230)
        for kind,obj in [('mold',mold),('glaze',glaze),('sample',sample)]:
            url=reverse('photos_manage',kwargs={'kind':kind,'pk':obj.pk})
            self.assertEqual(self.client.get(url).status_code,200)
            self.assertEqual(self.client.post(url,{'upload':'1'}).status_code,400)
            self.assertEqual(self.client.post(url,{'upload':'1','photos':[image_file()]}).status_code,302)
            self.assertEqual(obj.photos.count(),1)
            self.client.force_login(self.partner)
            self.assertEqual(self.client.get(url).status_code,404)
            self.client.force_login(self.owner)

    def test_editing_progress_recomputes_stage_from_latest_date_not_last_edited(self):
        today=timezone.localdate()
        old=Progress.objects.create(piece=self.piece,stage='raw',date=today-timedelta(days=2))
        latest=Progress.objects.create(piece=self.piece,stage='finished',date=today)
        photo=self.photos[0]
        photo.progress=old
        photo.save()
        url=reverse('progress_edit',args=[self.piece.pk,old.pk])
        self.assertEqual(self.client.post(url,{'date':old.date.isoformat(),'stage':'bisque','notes':'Corregido'}).status_code,302)
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.stage,'finished')
        old.refresh_from_db()
        self.assertEqual(old.notes,'Corregido')
        photo.refresh_from_db()
        self.assertEqual(photo.progress_id,old.pk)
        self.assertEqual(self.client.post(url,{'date':(today+timedelta(days=1)).isoformat(),'stage':'glazed','notes':''}).status_code,302)
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.stage,'glazed')

    def test_deleting_progress_preserves_photos_and_updates_stage(self):
        today=timezone.localdate()
        old=Progress.objects.create(piece=self.piece,stage='raw',date=today-timedelta(days=1))
        latest=Progress.objects.create(piece=self.piece,stage='finished',date=today)
        photo=self.photos[0]
        photo.progress=latest
        photo.save()
        url=reverse('progress_delete',args=[self.piece.pk,latest.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertTrue(Progress.objects.filter(pk=latest.pk).exists())
        self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,302)
        self.piece.refresh_from_db()
        photo.refresh_from_db()
        self.assertEqual(self.piece.stage,'raw')
        self.assertIsNone(photo.progress_id)
        self.assertTrue(photo.image.storage.exists(photo.image.name))
        self.client.post(reverse('progress_delete',args=[self.piece.pk,old.pk]),{'confirm_delete':'yes'})
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.stage,'process')

    def test_history_mutations_are_scoped_to_piece_and_owner(self):
        event=Progress.objects.create(piece=self.piece,stage='raw')
        glaze=Glaze.objects.create(owner=self.owner,name='Esmalte')
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze)
        other=Piece.objects.create(owner=self.owner,name='Otro')
        for name,record in [('progress_edit',event),('progress_delete',event),('glaze_use_delete',use)]:
            self.assertEqual(self.client.get(reverse(name,args=[other.pk,record.pk])).status_code,404)
            self.client.force_login(self.partner)
            url=reverse(name,args=[self.piece.pk,record.pk])
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,404)
            self.client.force_login(self.owner)

    def test_deleting_application_preserves_glaze_and_recipe(self):
        glaze=Glaze.objects.create(owner=self.owner,name='Esmalte')
        version=RecipeVersion.objects.create(glaze=glaze,number=1)
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze,recipe_version=version,layers=2)
        other=GlazeUse.objects.create(piece=self.piece,glaze=glaze,recipe_version=version,layers=1)
        url=reverse('glaze_use_delete',args=[self.piece.pk,use.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertTrue(GlazeUse.objects.filter(pk=use.pk).exists())
        self.assertEqual(self.client.post(url,{'confirm_delete':'yes'}).status_code,302)
        self.assertFalse(GlazeUse.objects.filter(pk=use.pk).exists())
        self.assertTrue(GlazeUse.objects.filter(pk=other.pk).exists())
        self.assertTrue(RecipeVersion.objects.filter(pk=version.pk).exists())

    def test_editing_application_after_shared_glaze_access_is_revoked_keeps_history_private(self):
        glaze=Glaze.objects.create(owner=self.partner,name='NOMBRE PRIVADO')
        version=RecipeVersion.objects.create(glaze=glaze,number=1)
        use=GlazeUse.objects.create(piece=self.piece,glaze=glaze,recipe_version=version,layers=2)
        url=reverse('glaze_use_edit',args=[self.piece.pk,use.pk])
        response=self.client.get(url)
        self.assertContains(response,'Material no disponible')
        self.assertNotContains(response,'NOMBRE PRIVADO')
        response=self.client.get(reverse('piece',args=[self.piece.pk]))
        self.assertContains(response,'Editar aplicación')
        self.assertNotContains(response,'NOMBRE PRIVADO')
        self.assertEqual(self.client.post(url,{'glaze':glaze.pk,'layers':3,'zone':'Exterior','method':'Pincel','grams':12}).status_code,302)
        use.refresh_from_db()
        self.assertEqual(use.recipe_version_id,version.pk)
        self.assertEqual(use.layers,3)

    def test_file_cleanup_is_discarded_on_rollback(self):
        from .services import schedule_photo_cleanup
        photo=self.photos[0]
        photo_id=photo.pk
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    photo.delete()
                    schedule_photo_cleanup([photo])
                    raise ValueError('rollback')
            except ValueError:
                pass
        self.assertTrue(Photo.objects.filter(pk=photo_id).exists())
        self.assertTrue(photo.image.storage.exists(photo.image.name))
