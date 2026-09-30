from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from .models import CandidateStatus, District, Election, Person, Suggestion


class PersonImportUploadForm(forms.Form):
    csv_file = forms.FileField(label='CSV file (columns: name, district)')
    source_label = forms.CharField(max_length=200, required=False, help_text='e.g. "2026 ballot filings, DCBOE 2026-09-15"')
    election = forms.ModelChoiceField(queryset=Election.objects.order_by('-year'))
    default_status = forms.ModelChoiceField(
        queryset=CandidateStatus.objects.order_by('display_order'),
        help_text='Applied to every candidate this batch creates -- override individual rows afterward if needed.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        declared = CandidateStatus.objects.filter(name='Declared Intention to Run').first()
        if declared:
            self.fields['default_status'].initial = declared.pk


class SuggestionForm(forms.ModelForm):
    # Honeypot: real users never see this field; bots that auto-fill every input on a form
    # do, so a non-empty value here marks the submission as spam (see SuggestionForm.is_spam).
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Suggestion
        fields = ['name', 'email', 'district', 'person', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 6}),
        }
        labels = {
            'name': 'Your name (optional)',
            'email': 'Your email (optional, in case we have questions)',
            'district': 'Related district (optional)',
            'person': 'Related person (optional)',
            'message': 'What should change?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['district'].queryset = District.objects.order_by('-redistricting_year', 'sort_order')
        self.fields['district'].required = False
        self.fields['person'].queryset = Person.objects.order_by('full_name')
        self.fields['person'].required = False
        self.fields['message'].help_text = (
            'Include names, dates, and a source link if you have one -- for a write-in '
            'candidate, a campaign website or social media post is ideal.'
        )

    def is_spam(self):
        return bool(self.cleaned_data.get('website'))


class SuggestionAdminForm(forms.ModelForm):
    """Renders Suggestion.structured_data as real fields instead of a raw JSON textarea. Which
    ones matter depends on suggestion_type (see suggestion_apply.py for what each handler reads)
    -- suggestion_admin.js shows/hides them accordingly and marks them required. district_id is
    taken from the existing `district` field rather than being entered a second time.

    REQUIRED_FIELDS_BY_TYPE below is enforced server-side in clean() -- the only thing that
    actually blocks a save. suggestion_admin.js mirrors the same map to mark fields with a
    visible "*" and (for plain inputs) the HTML required attribute, but that's a convenience,
    not the source of truth -- keep the two in sync if a type's required fields change.
    """
    REQUIRED_FIELDS_BY_TYPE = {
        Suggestion.TYPE_NEW_CANDIDATE: ['district', 'person_name', 'election_year'],
        Suggestion.TYPE_CANDIDATE_WITHDRAWS: ['candidate'],
        Suggestion.TYPE_COMMISSIONER_CHANGE: ['district', 'end_date'],
        Suggestion.TYPE_NEW_COMMISSIONER: ['district', 'person_name', 'start_date'],
    }

    person_name = forms.CharField(
        required=False, label='Person name',
        help_text='New candidate / new commissioner: full name.',
    )
    election_year = forms.IntegerField(required=False, help_text='New candidate.')
    ballot_or_write_in = forms.ChoiceField(
        choices=[('ballot', 'On the ballot'), ('write_in', 'Write-in')], required=False, initial='ballot',
        help_text='New candidate.',
    )
    start_date = forms.DateField(required=False, widget=AdminDateWidget, help_text='New commissioner.')
    end_date = forms.DateField(required=False, widget=AdminDateWidget, help_text='Commissioner resigned.')
    reason = forms.CharField(required=False, help_text='Commissioner resigned (optional).')

    class Meta:
        model = Suggestion
        exclude = ['structured_data']

    class Media:
        js = ['directory/js/suggestion_admin.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['candidate'].help_text = 'Candidate withdrew.'
        data = self.instance.structured_data or {}
        if self.instance.pk:
            self.fields['person_name'].initial = data.get('person_name', '')
            self.fields['election_year'].initial = data.get('election_year')
            self.fields['ballot_or_write_in'].initial = data.get('ballot_or_write_in', 'ballot')
            if not self.instance.candidate_id and data.get('candidate_id'):
                self.fields['candidate'].initial = data['candidate_id']
            self.fields['start_date'].initial = data.get('start_date')
            self.fields['end_date'].initial = data.get('end_date')
            self.fields['reason'].initial = data.get('reason', '')

    def clean(self):
        cleaned = super().clean()
        # These fields only matter for actually applying the suggestion, so only require them
        # once it's Approved -- rejecting (or still reviewing) a structured suggestion shouldn't
        # be blocked on filling in fields for a change that's not going to happen.
        if cleaned.get('status') != Suggestion.STATUS_APPROVED:
            return cleaned
        suggestion_type = cleaned.get('suggestion_type')
        type_label = dict(Suggestion.TYPE_CHOICES).get(suggestion_type, suggestion_type)
        for field_name in self.REQUIRED_FIELDS_BY_TYPE.get(suggestion_type, []):
            if not cleaned.get(field_name):
                self.add_error(field_name, f'Required to approve a "{type_label}" suggestion.')
        return cleaned

    def save(self, commit=True):
        suggestion_type = self.cleaned_data.get('suggestion_type')
        district = self.cleaned_data.get('district')
        structured_data = {}

        if suggestion_type == Suggestion.TYPE_NEW_CANDIDATE:
            if district:
                structured_data['district_id'] = district.id
            if self.cleaned_data.get('person_name'):
                structured_data['person_name'] = self.cleaned_data['person_name']
            if self.cleaned_data.get('election_year'):
                structured_data['election_year'] = self.cleaned_data['election_year']
            structured_data['ballot_or_write_in'] = self.cleaned_data.get('ballot_or_write_in') or 'ballot'
        elif suggestion_type == Suggestion.TYPE_CANDIDATE_WITHDRAWS:
            if self.cleaned_data.get('candidate'):
                structured_data['candidate_id'] = self.cleaned_data['candidate'].id
        elif suggestion_type == Suggestion.TYPE_COMMISSIONER_CHANGE:
            if district:
                structured_data['district_id'] = district.id
            if self.cleaned_data.get('end_date'):
                structured_data['end_date'] = self.cleaned_data['end_date'].isoformat()
            if self.cleaned_data.get('reason'):
                structured_data['reason'] = self.cleaned_data['reason']
        elif suggestion_type == Suggestion.TYPE_NEW_COMMISSIONER:
            if district:
                structured_data['district_id'] = district.id
            if self.cleaned_data.get('person_name'):
                structured_data['person_name'] = self.cleaned_data['person_name']
            if self.cleaned_data.get('start_date'):
                structured_data['start_date'] = self.cleaned_data['start_date'].isoformat()

        self.instance.structured_data = structured_data
        return super().save(commit=commit)
