from django.contrib import admin, messages
from django.urls import path
from simple_history.admin import SimpleHistoryAdmin

from . import admin_views, suggestion_apply
from .models import (
    ANC,
    ANCOverlap,
    Candidate,
    CandidateStatus,
    CommissionerTerm,
    District,
    DistrictOverlap,
    Election,
    ElectionResult,
    MapColor,
    Person,
    PersonImportBatch,
    PersonImportRow,
    SiteUpdate,
    Suggestion,
    Ward,
    WriteInWinner,
)


class CommissionerTermInline(admin.TabularInline):
    model = CommissionerTerm
    fk_name = 'person'
    extra = 0


class CandidateInline(admin.TabularInline):
    model = Candidate
    fk_name = 'person'
    extra = 0
    autocomplete_fields = ['district', 'election', 'status']


@admin.register(Person)
class PersonAdmin(SimpleHistoryAdmin):
    list_display = ['full_name', 'slug']
    search_fields = ['full_name']
    prepopulated_fields = {'slug': ('full_name',)}
    inlines = [CommissionerTermInline, CandidateInline]
    change_list_template = 'admin/directory/person/change_list.html'

    def get_urls(self):
        custom_urls = [
            path('import/', self.admin_site.admin_view(admin_views.person_import_upload), name='directory_person_import_upload'),
            path('import/<int:batch_id>/', self.admin_site.admin_view(admin_views.person_import_review), name='directory_person_import_review'),
            path('import/<int:batch_id>/apply/', self.admin_site.admin_view(admin_views.person_import_apply), name='directory_person_import_apply'),
        ]
        return custom_urls + super().get_urls()


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ['name', 'redistricting_year', 'councilmember']
    list_filter = ['redistricting_year']
    search_fields = ['councilmember']


@admin.register(ANC)
class ANCAdmin(admin.ModelAdmin):
    list_display = ['name', 'redistricting_year']
    list_filter = ['redistricting_year']
    search_fields = ['designator']


@admin.register(ANCOverlap)
class ANCOverlapAdmin(admin.ModelAdmin):
    list_display = ['from_anc', 'to_anc', 'overlap_percentage']
    autocomplete_fields = ['from_anc', 'to_anc']


@admin.register(MapColor)
class MapColorAdmin(admin.ModelAdmin):
    list_display = ['id', 'hex_code']
    search_fields = ['hex_code']


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ['designator', 'redistricting_year', 'anc', 'ward']
    list_filter = ['redistricting_year', 'ward']
    search_fields = ['designator']
    autocomplete_fields = ['anc', 'ward', 'map_color', 'neighbors']


@admin.register(DistrictOverlap)
class DistrictOverlapAdmin(admin.ModelAdmin):
    list_display = ['from_district', 'to_district', 'overlap_percentage']
    autocomplete_fields = ['from_district', 'to_district']


@admin.register(CommissionerTerm)
class CommissionerTermAdmin(SimpleHistoryAdmin):
    list_display = ['person', 'district', 'start_date', 'end_date', 'confirmed_not_running']
    list_filter = ['confirmed_not_running']
    search_fields = ['person__full_name', 'district__designator']
    autocomplete_fields = ['person', 'district']


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ['year', 'election_date', 'petition_open_date', 'petition_close_date']
    search_fields = ['year']


@admin.register(CandidateStatus)
class CandidateStatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'publish_candidate', 'count_as_candidate', 'display_order']
    search_fields = ['name']


@admin.register(Candidate)
class CandidateAdmin(SimpleHistoryAdmin):
    list_display = ['person', 'election', 'district', 'status']
    list_filter = ['election', 'status']
    search_fields = ['person__full_name', 'district__designator']
    autocomplete_fields = ['person', 'district', 'election', 'status']


@admin.register(ElectionResult)
class ElectionResultAdmin(SimpleHistoryAdmin):
    list_display = ['election', 'district', 'candidate', 'candidate_name_raw', 'votes', 'is_winner']
    list_filter = ['election', 'is_winner', 'is_write_in_winner']
    search_fields = ['candidate__person__full_name', 'candidate_name_raw', 'district__designator']
    autocomplete_fields = ['election', 'district', 'candidate']


@admin.register(SiteUpdate)
class SiteUpdateAdmin(SimpleHistoryAdmin):
    list_display = ['date', 'is_published']
    list_filter = ['is_published']
    ordering = ['-date']


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'submitted_at', 'status', 'suggestion_type', 'district', 'person', 'name', 'applied_at']
    list_filter = ['status', 'suggestion_type']
    search_fields = ['name', 'email', 'message']
    autocomplete_fields = ['district', 'person']
    readonly_fields = ['submitted_at', 'applied_at', 'resulting_person', 'resulting_district']
    actions = ['mark_approved', 'mark_rejected', 'apply_suggestions']

    @admin.action(description='Mark selected suggestions as approved')
    def mark_approved(self, request, queryset):
        queryset.update(status=Suggestion.STATUS_APPROVED)

    @admin.action(description='Mark selected suggestions as rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(status=Suggestion.STATUS_REJECTED)

    @admin.action(description='Apply selected suggestions (structured types only)')
    def apply_suggestions(self, request, queryset):
        applied = 0
        for suggestion in queryset:
            if suggestion.applied_at:
                self.message_user(request, f'Suggestion #{suggestion.pk} was already applied on {suggestion.applied_at} -- skipped.', level=messages.WARNING)
                continue
            try:
                suggestion_apply.apply_suggestion(suggestion)
            except suggestion_apply.SuggestionApplyError as e:
                self.message_user(request, f'Suggestion #{suggestion.pk}: {e}', level=messages.ERROR)
            else:
                applied += 1
        if applied:
            self.message_user(request, f'Applied {applied} suggestion(s).', level=messages.SUCCESS)


@admin.register(WriteInWinner)
class WriteInWinnerAdmin(SimpleHistoryAdmin):
    list_display = ['candidate_name_raw', 'election', 'district', 'person']
    autocomplete_fields = ['election', 'district', 'person']


class PersonImportRowInline(admin.TabularInline):
    model = PersonImportRow
    extra = 0
    fields = ['raw_name', 'raw_district_designator', 'district', 'decision', 'chosen_person', 'best_match_score', 'applied']
    readonly_fields = ['best_match_score']
    autocomplete_fields = ['district', 'chosen_person']


@admin.register(PersonImportBatch)
class PersonImportBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'source_label', 'election', 'default_status', 'review_link']
    inlines = [PersonImportRowInline]

    @admin.display(description='Review')
    def review_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:directory_person_import_review', kwargs={'batch_id': obj.pk})
        return format_html('<a href="{}">Review &amp; apply &rarr;</a>', url)
