from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from django.http import HttpResponse

urlpatterns = [
    path('', include('homepage.urls')),
    path('fintech/', include('fintech.urls')),
    path('admin/', admin.site.urls),
    path('robots.txt', 
         lambda request: HttpResponse(
             "User-agent: *\nAllow: /\n\n"
             "Sitemap: https://littlecapa.com/sitemap.xml", 
             content_type='text/plain'
         ), 
         name='robots_txt'
    ),
    path('sitemap.xml', 
         lambda request: HttpResponse(
             '''<?xml version="1.0"?>
             <urlset><url><loc>https://littlecapa.com/</loc></url></urlset>''',
             content_type='application/xml'
         )),
]

# Standard-Weg für Development (DEBUG=True)
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# TRICK für Production (DEBUG=False)
else:
    # Wir sagen Django explizit: "Ja, du darfst diese Dateien servieren, 
    # auch wenn du glaubst, du solltest es nicht tun."
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
        re_path(r'^static/(?P<path>.*)$', serve, {
            'document_root': settings.STATIC_ROOT,
        }),
    ]