# views

from django.http import HttpResponse
from django.template import Context, Template

def home(request):
    return HttpResponse("Hello")

def template(request):
    t = Template('Hello {{ name }}')
    c = Context({'name': 'yourname'})
    html = t.render(c)
    return HttpResponse(html)
