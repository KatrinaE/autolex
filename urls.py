from django.conf.urls.defaults import *
from django.views.generic.simple import direct_to_template

from translate.views import *

urlpatterns = patterns('translate.views',
    url(r"^approve-translations/$", approve_translations, {}, name="user-add"),
    url(r'^translation/(?P<group_id>[\w-]+)/$', translation_detail, {}, name="translation-detail"),
    url(r'^(?P<community_name>[\w-]+)/node/(?P<node_name>[\w-]+)/translate/$',
        node_translate, {}, name="node-translate"),
)
