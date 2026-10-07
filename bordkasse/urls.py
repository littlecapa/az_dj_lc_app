from django.urls import path

from . import views

app_name = 'bordkasse'

urlpatterns = [
    path('',                                   views.toern_list,       name='index'),         # /bordkasse/
    path('<slug:slug>/',                       views.toern_detail,     name='detail'),        # /bordkasse/kroatien-2026/
    path('<slug:slug>/abrechnung/',            views.abrechnung,       name='abrechnung'),
    path('<slug:slug>/export.xlsx',            views.export_xlsx,      name='export'),
    path('<slug:slug>/api/state/',             views.api_state,        name='api_state'),
    path('<slug:slug>/api/crew/',              views.api_crew_add,     name='api_crew_add'),
    path('<slug:slug>/api/crew/<int:pk>/',     views.api_crew_rename,  name='api_crew_rename'),
    path('<slug:slug>/api/tx/',                views.api_tx_add,       name='api_tx_add'),
    path('<slug:slug>/api/tx/<int:pk>/',       views.api_tx_edit,      name='api_tx_edit'),
    path('<slug:slug>/api/tx/<int:pk>/delete/', views.api_tx_delete,   name='api_tx_delete'),
    path('<slug:slug>/api/shop/',              views.api_shop_add,     name='api_shop_add'),
    path('<slug:slug>/api/shop/<int:pk>/',     views.api_shop_update,  name='api_shop_update'),
    path('<slug:slug>/api/shop/<int:pk>/delete/', views.api_shop_delete, name='api_shop_delete'),
]
