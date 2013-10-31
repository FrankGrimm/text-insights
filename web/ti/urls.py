from django.conf.urls import patterns, include, url
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = patterns('ti.views',
    url(r'^$', 'home', name='home'),
    url(r'^login$', 'login_view', name='login'),
    url(r'^logout$', 'logout_view', name='logout'),
    url(r'^overview$', 'overview_view', name='overview'),
    url(r'^base.js$', 'base_js', name='base_js'),
    url(r'^base.css$', 'base_css', name='base_css'),
    url(r'^template$', 'template', name='template'),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
