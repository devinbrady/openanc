from django import forms

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
