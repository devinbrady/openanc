from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


# DC redraws ANC/SMD boundaries roughly once a decade. Rather than one "current" table plus an
# archive, every spatial model keeps rows for every redistricting era side by side, distinguished
# by `redistricting_year`. settings.CURRENT_REDISTRICTING_YEAR says which era is "live" today.

class Ward(models.Model):
    ward_number = models.PositiveSmallIntegerField()
    redistricting_year = models.PositiveSmallIntegerField()
    councilmember = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['redistricting_year', 'ward_number']
        constraints = [
            models.UniqueConstraint(
                fields=['ward_number', 'redistricting_year'], name='unique_ward_per_cycle'
            )
        ]

    def __str__(self):
        return f'Ward {self.ward_number} ({self.redistricting_year})'

    def get_absolute_url(self):
        return reverse('directory:ward_detail', kwargs={'year': self.redistricting_year, 'number': self.ward_number})

    @property
    def name(self):
        return f'Ward {self.ward_number}'


class ANC(models.Model):
    # e.g. "1A" -- ward number + commission letter. Not an FK to Ward: an ANC's districts can
    # span more than one ward (ANC 3G does), so the relationship only exists via District.
    designator = models.CharField(max_length=4)
    redistricting_year = models.PositiveSmallIntegerField()

    dc_oanc_link = models.URLField(blank=True)
    anc_homepage_link = models.URLField(blank=True)
    twitter_link = models.URLField(blank=True)
    centroid_lon = models.FloatField(null=True, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    area = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'ANC'
        verbose_name_plural = 'ANCs'
        ordering = ['redistricting_year', 'designator']
        constraints = [
            models.UniqueConstraint(
                fields=['designator', 'redistricting_year'], name='unique_anc_per_cycle'
            )
        ]

    def __str__(self):
        return f'ANC {self.designator} ({self.redistricting_year})'

    def get_absolute_url(self):
        return reverse('directory:anc_detail', kwargs={'year': self.redistricting_year, 'designator': self.designator})

    @property
    def name(self):
        return f'ANC {self.designator}'


class ANCOverlap(models.Model):
    """How much an ANC's territory overlaps one from the other redistricting era."""
    from_anc = models.ForeignKey(ANC, related_name='overlaps_from', on_delete=models.CASCADE)
    to_anc = models.ForeignKey(ANC, related_name='overlaps_to', on_delete=models.CASCADE)
    # A 0-1 fraction (matches the source CSV), not a 0-100 percentage -- multiply by 100
    # when displaying (see the `as_percentage` template filter).
    overlap_percentage = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_anc', 'to_anc'], name='unique_anc_overlap')
        ]

    def __str__(self):
        return f'{self.from_anc} -> {self.to_anc} ({self.overlap_percentage * 100:.1f}%)'


class MapColor(models.Model):
    hex_code = models.CharField(max_length=7)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.hex_code


class District(models.Model):
    """A Single Member District (SMD), the base electoral unit within an ANC."""
    # e.g. "1A01" -- matches the ANC designator plus a 2-digit district number.
    designator = models.CharField(max_length=8)
    redistricting_year = models.PositiveSmallIntegerField()
    anc = models.ForeignKey(ANC, related_name='districts', on_delete=models.PROTECT)
    ward = models.ForeignKey(Ward, related_name='districts', on_delete=models.PROTECT)
    map_color = models.ForeignKey(
        MapColor, related_name='districts', null=True, blank=True, on_delete=models.SET_NULL
    )
    sort_order = models.PositiveIntegerField(default=0)

    centroid_lon = models.FloatField(null=True, blank=True)
    centroid_lat = models.FloatField(null=True, blank=True)
    area = models.PositiveIntegerField(null=True, blank=True)

    neighbors = models.ManyToManyField('self', blank=True)

    notes = models.TextField(blank=True)
    description = models.TextField(blank=True)
    landmarks = models.TextField(blank=True)

    class Meta:
        verbose_name = 'district'
        ordering = ['redistricting_year', 'sort_order']
        constraints = [
            models.UniqueConstraint(
                fields=['designator', 'redistricting_year'], name='unique_district_per_cycle'
            )
        ]

    def __str__(self):
        return f'SMD {self.designator} ({self.redistricting_year})'

    def get_absolute_url(self):
        return reverse('directory:district_detail', kwargs={'year': self.redistricting_year, 'designator': self.designator})

    @property
    def current_commissioner_term(self):
        today = timezone.localdate()
        return self.commissioner_terms.select_related('person').filter(start_date__lte=today, end_date__gte=today).first()

    @property
    def future_commissioner_term(self):
        today = timezone.localdate()
        return self.commissioner_terms.filter(start_date__gt=today).order_by('start_date').first()


class DistrictOverlap(models.Model):
    """How much a district's territory overlaps one from the other redistricting era."""
    from_district = models.ForeignKey(District, related_name='overlaps_from', on_delete=models.CASCADE)
    to_district = models.ForeignKey(District, related_name='overlaps_to', on_delete=models.CASCADE)
    # A 0-1 fraction (matches the source CSV), not a 0-100 percentage -- multiply by 100
    # when displaying (see the `as_percentage` template filter).
    overlap_percentage = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_district', 'to_district'], name='unique_district_overlap')
        ]

    def __str__(self):
        return f'{self.from_district} -> {self.to_district} ({self.overlap_percentage * 100:.1f}%)'


class Person(models.Model):
    """Anyone who has ever been a commissioner and/or a candidate."""
    full_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    twitter_link = models.URLField(blank=True)
    mastodon_link = models.URLField(blank=True)
    facebook_link = models.URLField(blank=True)
    website_link = models.URLField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse('directory:person_detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.full_name) or 'person'
            slug = base_slug
            suffix = 1
            while Person.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix += 1
                slug = f'{base_slug}-{suffix}'
            self.slug = slug
        super().save(*args, **kwargs)


class CommissionerTerm(models.Model):
    """One continuous stretch of a person representing a district, at most 2 years."""
    person = models.ForeignKey(Person, related_name='commissioner_terms', on_delete=models.CASCADE)
    district = models.ForeignKey(District, related_name='commissioner_terms', on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    # True for the mass Jan 2, 2019 inauguration date used when the exact historical start date
    # wasn't recorded -- lets the UI show "~2019" instead of a falsely-precise date.
    start_date_is_approximate = models.BooleanField(default=False)
    # Only meaningful for the current term: a manually-confirmed "not running for reelection".
    confirmed_not_running = models.BooleanField(default=False)

    history = HistoricalRecords()

    class Meta:
        ordering = ['district__designator', 'start_date']

    def __str__(self):
        return f'{self.person} — {self.district} ({self.start_date} to {self.end_date})'

    def clean(self):
        if self.end_date <= self.start_date:
            raise ValidationError('end_date must be after start_date.')
        if self.end_date - self.start_date > timedelta(days=731):
            raise ValidationError('A commissioner term cannot be longer than 2 years.')
        # A term handing off to the next one on the same day (one's end_date == the next one's
        # start_date) is the normal same-day transition used throughout the real data -- only a
        # genuine overlap (more than a shared boundary day) is invalid.
        overlapping = CommissionerTerm.objects.filter(
            district=self.district, start_date__lt=self.end_date, end_date__gt=self.start_date,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError(f'{self.district} already has a commissioner term overlapping this date range.')

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.start_date <= today <= self.end_date

    @property
    def is_future(self):
        return self.start_date > timezone.localdate()

    @property
    def is_former(self):
        return self.end_date < timezone.localdate()

    @property
    def term_label(self):
        start = f'~{self.start_date.year}' if self.start_date_is_approximate else self.start_date.strftime('%B %-d, %Y')
        return f'{start} to {self.end_date.strftime("%B %-d, %Y")}'

    def covers_date(self, a_date):
        return self.start_date <= a_date <= self.end_date


class Election(models.Model):
    year = models.PositiveSmallIntegerField(unique=True)
    election_date = models.DateField(null=True, blank=True)
    petition_open_date = models.DateField(null=True, blank=True)
    petition_close_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['year']

    def __str__(self):
        return str(self.year)

    @property
    def is_petition_window_open(self):
        today = timezone.localdate()
        if not (self.petition_open_date and self.petition_close_date):
            return False
        return self.petition_open_date <= today <= self.petition_close_date


class CandidateStatus(models.Model):
    """Mutable status enum -- 'Pulled Papers for Ballot' toggles count_as_candidate based on
    whether today falls in that election's petition window, so this can't be a static choices
    tuple."""
    name = models.CharField(max_length=50, unique=True)
    publish_candidate = models.BooleanField(default=True)
    count_as_candidate = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'candidate statuses'
        ordering = ['display_order']

    def __str__(self):
        return self.name


class Candidate(models.Model):
    person = models.ForeignKey(Person, related_name='candidacies', on_delete=models.CASCADE)
    election = models.ForeignKey(Election, related_name='candidates', on_delete=models.CASCADE)
    district = models.ForeignKey(District, related_name='candidates', on_delete=models.CASCADE)

    # The effective/published status (may be a manual override of dcboe_status).
    status = models.ForeignKey(CandidateStatus, related_name='candidates', on_delete=models.PROTECT)
    dcboe_status = models.CharField(max_length=50, blank=True)

    pickup_date = models.DateField(null=True, blank=True)
    filed_date = models.DateField(null=True, blank=True)
    write_in_winner_dcboe = models.BooleanField(default=False)

    source = models.CharField(max_length=50, blank=True)
    source_description = models.TextField(blank=True)
    source_link = models.URLField(blank=True)

    dcboe_source_link = models.URLField(blank=True)
    dcboe_updated_at = models.DateField(null=True, blank=True)

    manual_status_source = models.CharField(max_length=200, blank=True)
    manual_status_source_link = models.URLField(blank=True)
    manual_status_updated_at = models.DateField(null=True, blank=True)

    content_updated_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['election__year', 'district__designator']
        constraints = [
            models.UniqueConstraint(fields=['election', 'person'], name='unique_candidate_per_election')
        ]

    def __str__(self):
        return f'{self.person} — {self.district} ({self.election.year})'

    @property
    def is_incumbent(self):
        """Was this person the sitting commissioner on this district's election day?"""
        if not self.election.election_date:
            return False
        return self.district.commissioner_terms.filter(
            person=self.person,
            start_date__lte=self.election.election_date,
            end_date__gte=self.election.election_date,
        ).exists()


class ElectionResult(models.Model):
    """One row per (election, district, candidate) with certified DCBOE vote totals.

    candidate is null for the single "combined write-ins" row DCBOE reports per district --
    individual write-in vote counts are never published, only the certified winner (see
    WriteInWinner) and the combined total.
    """
    election = models.ForeignKey(Election, related_name='results', on_delete=models.CASCADE)
    district = models.ForeignKey(District, related_name='results', on_delete=models.CASCADE)
    candidate = models.ForeignKey(
        Candidate, related_name='results', null=True, blank=True, on_delete=models.SET_NULL
    )
    candidate_name_raw = models.CharField(max_length=200, blank=True)

    votes = models.PositiveIntegerField()
    ranking = models.PositiveSmallIntegerField(null=True, blank=True)
    is_winner = models.BooleanField(default=False)
    is_write_in_winner = models.BooleanField(default=False)
    margin_of_victory = models.IntegerField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['election__year', 'district__designator', 'ranking']

    def __str__(self):
        name = self.candidate or self.candidate_name_raw or 'Write-ins combined'
        return f'{name} — {self.district} ({self.election.year}): {self.votes} votes'


class SiteUpdate(models.Model):
    """An entry on the public Updates page -- edited in the admin instead of updates.md."""
    date = models.DateField()
    body = models.TextField(help_text='HTML is allowed (links, paragraphs, etc).')
    # False for drafts generated by the draft_site_update management command -- kept off the
    # public page until a human reviews/edits and flips this on.
    is_published = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'Update on {self.date}'


class Suggestion(models.Model):
    """A public submission -- a write-in candidate, a correction, a commissioner change -- for
    a moderator to review and apply in the admin. Replaces emailing edits in directly.

    The public submission form only ever sets the free-text fields below (name/email/district/
    person/message) and leaves suggestion_type at its 'general' default -- a moderator
    re-classifies a suggestion and fills in structured_data during local review, then uses the
    "Apply selected suggestions" admin action (see suggestion_apply.py) to apply it directly for
    the four structured types. 'general' has no automatic handler and stays a manual free-text
    edit, exactly like before this feature existed.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    TYPE_GENERAL = 'general'
    TYPE_NEW_CANDIDATE = 'new_candidate'
    TYPE_CANDIDATE_WITHDRAWS = 'candidate_withdraws'
    TYPE_COMMISSIONER_CHANGE = 'commissioner_change'
    TYPE_NEW_COMMISSIONER = 'new_commissioner'
    TYPE_CHOICES = [
        (TYPE_GENERAL, 'General edit / suggestion (free text)'),
        (TYPE_NEW_CANDIDATE, 'New candidate declared'),
        (TYPE_CANDIDATE_WITHDRAWS, 'Candidate withdraws'),
        (TYPE_COMMISSIONER_CHANGE, 'Commissioner stops serving early'),
        (TYPE_NEW_COMMISSIONER, 'New commissioner appointed'),
    ]

    submitted_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    district = models.ForeignKey(
        District, related_name='suggestions', null=True, blank=True, on_delete=models.SET_NULL
    )
    person = models.ForeignKey(
        Person, related_name='suggestions', null=True, blank=True, on_delete=models.SET_NULL
    )
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    moderator_notes = models.TextField(blank=True)

    # Set by a moderator during review (not the public submitter) -- see suggestion_apply.py for
    # what structured_data needs to contain for each type.
    suggestion_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_GENERAL)
    structured_data = models.JSONField(default=dict, blank=True)

    # Set automatically by suggestion_apply.apply_suggestion() -- what applying this suggestion
    # actually did, for display in the admin. Never hand-edited.
    applied_at = models.DateTimeField(null=True, blank=True)
    resulting_person = models.ForeignKey(Person, related_name='+', null=True, blank=True, on_delete=models.SET_NULL)
    resulting_district = models.ForeignKey(District, related_name='+', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'Suggestion #{self.pk} ({self.get_status_display()})'


class WriteInWinner(models.Model):
    """A write-in candidate certified by DCBOE as having won (an accepted Affirmation of
    Write-in Candidacy). Individual write-in vote counts aren't public; only who won is."""
    election = models.ForeignKey(Election, related_name='write_in_winners', on_delete=models.CASCADE)
    district = models.ForeignKey(District, related_name='write_in_winners', on_delete=models.CASCADE)
    person = models.ForeignKey(
        Person, related_name='write_in_wins', null=True, blank=True, on_delete=models.SET_NULL
    )
    candidate_name_raw = models.CharField(max_length=200)

    history = HistoricalRecords()

    def __str__(self):
        return f'{self.candidate_name_raw} — {self.district} ({self.election.year})'


class PersonImportBatch(models.Model):
    """One CSV upload through the admin's person-import tool (directory/admin_views.py) --
    replaces the old scripts/match_people.py CSV-round-trip with review state that lives in the
    database instead of hand-edited files."""
    created_at = models.DateTimeField(auto_now_add=True)
    source_label = models.CharField(max_length=200, blank=True)
    election = models.ForeignKey(Election, related_name='import_batches', null=True, blank=True, on_delete=models.SET_NULL)
    default_status = models.ForeignKey(CandidateStatus, related_name='import_batches', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Import batch #{self.pk} ({self.source_label or "unlabeled"})'


class PersonImportRow(models.Model):
    DECISION_PENDING = 'pending'
    DECISION_LINK = 'link'
    DECISION_NEW = 'new'
    DECISION_SKIP = 'skip'
    DECISION_CHOICES = [
        (DECISION_PENDING, 'Pending'),
        (DECISION_LINK, 'Link to existing'),
        (DECISION_NEW, 'Create new'),
        (DECISION_SKIP, 'Skip'),
    ]

    batch = models.ForeignKey(PersonImportBatch, related_name='rows', on_delete=models.CASCADE)
    raw_name = models.CharField(max_length=200)
    raw_district_designator = models.CharField(max_length=8, blank=True)
    district = models.ForeignKey(District, related_name='+', null=True, blank=True, on_delete=models.SET_NULL)

    # Up to 5 {person_id, full_name, score} dicts, best first -- populated by directory/matching.py.
    match_candidates_json = models.JSONField(default=list, blank=True)
    best_match_score = models.FloatField(null=True, blank=True)

    decision = models.CharField(max_length=10, choices=DECISION_CHOICES, default=DECISION_PENDING)
    chosen_person = models.ForeignKey(Person, related_name='+', null=True, blank=True, on_delete=models.SET_NULL)
    applied = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.raw_name} ({self.get_decision_display()})'
