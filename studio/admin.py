from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Piece, Mold, Glaze, Circle, Gallery
from .permissions import can_edit, editable_materials, manageable_circles

@admin.register(User)
class CanelaUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Canela', {'fields': ('display_name','bio')}),)
    list_display = ('username','display_name','email','date_joined','is_active','is_staff')
    search_fields = ('username','display_name','email')

@admin.register(Glaze)
class MaterialAdmin(admin.ModelAdmin):
    exclude = ('shared_groups',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=editable_materials(request.user, self.model).values('pk'))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'group':
            kwargs['queryset'] = manageable_circles(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or can_edit(obj, request.user))

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or can_edit(obj, request.user))


admin.site.register(Mold, MaterialAdmin)

for model in (Piece,Circle,Gallery):
    admin.site.register(model)
admin.site.site_header = _('Canela · Administración')
admin.site.site_title = 'Canela'
