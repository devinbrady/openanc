// Shows only the structured-data fields relevant to the selected suggestion type, and marks
// which of those (plus district/candidate) are required, on the Suggestion admin change form
// (see SuggestionAdminForm in forms.py). This is a convenience layer only -- the actual save
// block is server-side validation in SuggestionAdminForm.clean(); keep REQUIRED_FIELDS_BY_TYPE
// there in sync with requiredFieldsByType below if a type's required fields ever change.
document.addEventListener('DOMContentLoaded', function () {
    var typeField = document.getElementById('id_suggestion_type');
    var statusField = document.getElementById('id_status');
    if (!typeField) return;

    var visibleFieldsByType = {
        general: [],
        new_candidate: ['person_name', 'election_year', 'ballot_or_write_in'],
        candidate_withdraws: ['candidate'],
        commissioner_change: ['end_date', 'reason'],
        new_commissioner: ['person_name', 'start_date'],
    };
    var allStructuredFields = [
        'person_name', 'election_year', 'ballot_or_write_in', 'candidate', 'start_date', 'end_date', 'reason',
    ];

    var requiredFieldsByType = {
        general: [],
        new_candidate: ['district', 'person_name', 'election_year'],
        candidate_withdraws: ['candidate'],
        commissioner_change: ['district', 'end_date'],
        new_commissioner: ['district', 'person_name', 'start_date'],
    };
    var allConditionallyRequiredFields = ['district', 'person_name', 'election_year', 'candidate', 'start_date', 'end_date'];
    // district/candidate use the admin's autocomplete widget -- a hidden <select> behind a JS
    // search box. Browsers won't reliably show the native "required" validation popup on a
    // hidden element, so those two get the visible "*" only; server-side clean() still enforces
    // them either way.
    var AUTOCOMPLETE_FIELDS = ['district', 'candidate'];

    function rowFor(fieldName) {
        var input = document.getElementById('id_' + fieldName);
        return input ? input.closest('.form-row') : null;
    }

    function markRequired(fieldName, isRequired) {
        var input = document.getElementById('id_' + fieldName);
        if (!input) return;
        if (AUTOCOMPLETE_FIELDS.indexOf(fieldName) === -1) {
            input.required = isRequired;
        }
        var label = document.querySelector('label[for="' + input.id + '"]');
        if (!label) return;
        var star = label.querySelector('.required-star');
        if (isRequired && !star) {
            star = document.createElement('span');
            star.className = 'required-star';
            star.textContent = ' *';
            star.style.color = '#e33';
            label.appendChild(star);
        } else if (!isRequired && star) {
            star.remove();
        }
    }

    function update() {
        var type = typeField.value;

        var visible = visibleFieldsByType[type] || [];
        allStructuredFields.forEach(function (fieldName) {
            var row = rowFor(fieldName);
            if (row) {
                row.style.display = visible.indexOf(fieldName) === -1 ? 'none' : '';
            }
        });

        // These fields only matter for actually applying the suggestion -- only mark them
        // required once Status is set to Approved, matching SuggestionAdminForm.clean(). Saving
        // as Pending or Rejected never requires them.
        var isApproved = !statusField || statusField.value === 'approved';
        var required = isApproved ? (requiredFieldsByType[type] || []) : [];
        allConditionallyRequiredFields.forEach(function (fieldName) {
            markRequired(fieldName, required.indexOf(fieldName) !== -1);
        });
    }

    typeField.addEventListener('change', update);
    if (statusField) statusField.addEventListener('change', update);
    update();
});
