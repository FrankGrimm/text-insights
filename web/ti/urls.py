from django.conf.urls import patterns, include, url
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = patterns('ti.views', 
    url(r'^$', 'home', name='hello'),
    url(r'^template$', 'template', name='template'),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
