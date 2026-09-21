# fintech/urls_demo.py
#
# Login-freier Demo-Bereich unter /demo/fintech/. Spiegelt einen Teil der
# Pfade aus fintech/urls.py (gleiche View-Funktionen, aufgerufen mit
# demo=True), damit Holdings/Watchlisten/News ohne Login angesehen werden
# können. Holdings werden dabei auf Holdings.demo=True gefiltert, siehe
# login_required_unless_demo in views.py.
#
# app_name wird hier bewusst NICHT gesetzt — beim include() in
# azureproject/urls.py wird derselbe App-Namespace "fintech" wie für die
# normale App vergeben (nur mit eigenem Instance-Namespace "fintech_demo"),
# damit {% url 'fintech:...' %} in den (unveränderten) Templates automatisch
# im jeweils aktuellen Bereich bleibt.

from django.urls import path
from . import views

urlpatterns = [
    path('', views.fintech_index, {'demo': True}, name="fintech-index"),
    path('overall/', views.portfolio_overall, {'demo': True}, name="portfolio-overall"),
    path('portfolio/', views.portfolio_performance, {'demo': True}, name="portfolio-performance"),
    path('winner/', views.portfolio_winners, {'demo': True}, name="portfolio-winners"),
    path('portfolio/<slug:category_slug>/', views.portfolio_category_detail, {'demo': True}, name="portfolio-category-detail"),
    path('watchlist-performance/', views.watchlist_performance, {'demo': True}, name="watchlist-performance"),
    path('watchlists_all/', views.watchlists_all, {'demo': True}, name="watchlists-all"),
    path('watchlist-performance/<path:watchlist_name>/', views.watchlist_detail, {'demo': True}, name="watchlist-detail"),
    path('news/', views.news, {'demo': True}, name="news"),
    path('news-feed/', views.news_feed, {'demo': True}, name="news-feed"),
]
