# views

from django.http import HttpResponse
from django.template import Context, loader
import datetime
import os
import ti

def home(request):
    return HttpResponse("Hello" + ti.__file__)

def template(request):
    ctx = {'name': 'yourname','now':datetime.datetime.now()}
    return renderTemplate(request, "hello", ctx)

def renderTemplate(request, templateId, context):
    t = loader.get_template(templateId)
    c = Context(context)
    html = t.render(c)
    return HttpResponse(html)
