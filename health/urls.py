from django.urls import path
from . import views

urlpatterns = [
    path('bp/', views.BloodPressureListView.as_view(), name='bp_list'),
    path('bp/export/', views.get_export_csv, name='bp_export'),
]
