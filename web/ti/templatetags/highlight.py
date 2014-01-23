from django import template
from django.utils.safestring import mark_safe


register = template.Library()

@register.filter
def highlight(text, word):
    return mark_safe(text.replace(word, "<span style='color:red;'>%s</span>" % word))
