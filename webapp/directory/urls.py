from django.urls import path, register_converter

from . import views


class DesignatorConverter:
    """A district designator like '1A01', or '3/4G01' for the handful that span two wards.
    The '/' can't survive in a URL segment, so it's swapped for '-' there and back here."""
    regex = '[A-Za-z0-9-]+'

    def to_python(self, value):
        return value.upper().replace('-', '/')

    def to_url(self, value):
        return value.replace('/', '-')


register_converter(DesignatorConverter, 'designator')

app_name = 'directory'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('districts/', views.DistrictListView.as_view(), name='district_list'),
    path('districts/<int:year>/<designator:designator>/', views.DistrictDetailView.as_view(), name='district_detail'),
    path('ancs/<int:year>/<designator:designator>/', views.ANCDetailView.as_view(), name='anc_detail'),
    path('wards/<int:year>/<int:number>/', views.WardDetailView.as_view(), name='ward_detail'),
    path('people/', views.PersonListView.as_view(), name='person_list'),
    path('people/<slug:slug>/', views.PersonDetailView.as_view(), name='person_detail'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('updates/', views.UpdatesView.as_view(), name='updates'),
    path('counts/', views.CountsView.as_view(), name='counts'),
    path('contested/', views.ContestedMapView.as_view(), name='contested'),
    path('suggest/', views.SuggestionCreateView.as_view(), name='suggest_edit'),
    path(
        'api/districts/<int:year>/<designator:designator>/summary/',
        views.district_summary,
        name='district_summary',
    ),
]
