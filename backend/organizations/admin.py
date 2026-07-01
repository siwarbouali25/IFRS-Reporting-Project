from django.contrib import admin

from .models import Bank


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "sector", "created_at")
    search_fields = ("code", "name", "country", "sector")
    list_filter = ("country", "sector")