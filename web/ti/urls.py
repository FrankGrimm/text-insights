from django.conf.urls import patterns, include, url

urlpatterns = patterns('ti.views', 
    url(r'^$', 'home', name='hello'),
)
