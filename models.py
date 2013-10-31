# Python imports
from datetime import datetime
import time
import urllib2
import urllib
import simplejson
import uuid

# Django imports
from django.contrib.auth.models import User
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.utils import translation
from util.middleware.threadlocals import get_current_user

# Project imports
from django.conf import settings


def get_google_translate_user():
    """ Returns the User object responsible for creating Google-updated Translation objects.  """
    return User.objects.get(username=settings.GOOGLE_TRANSLATE_USERNAME)


LANGUAGE_CHOICES = (
    ('af' ,'Afrikaans'),
    ('sq' , 'Albanian'),
    ('am', 'Amharic'),
    ('ar', 'Arabic'),
    ('hy', 'Armenian'),
    ('az', 'Azerbaijani'),
    ('eu', 'Basque'),
    ('be', 'Belarusian'),
    ('bn', 'Bengali'),
    ('bh', 'Biwari'),
    ('br', 'Breton'),
    ('bg', 'Bulgarian'),
    ('my', 'Burmese'),
    ('ca', 'Catalan'),
    ('chr', 'Cherokee'),
    ('zh', 'Chinese'),
    ('zh-CN', 'Chinese Simplified'),
    ('zh-TW', 'Chinese Traditional'),
    ('co', 'Corsican'),
    ('hr', 'Croatian'),
    ('cs', 'Czech'),
    ('da', 'Danish'),
    ('dv', 'Dhivehi'),
    ('nl', 'Dutch'),
    ('en', 'English'),
    ('eo', 'Esperanto'),
    ('fo', 'Faroese'),
    ('et', 'Estonian'),
    ('tl', 'Filipino'),
    ('fi', 'Finnish'),
    ('fr', 'French'),
    ('fy', 'Frisian'),
    ('gl', 'Galician'),
    ('ka', 'Georigian'),
    ('de', 'German'),
    ('el', 'Greek'),
    ('gu', 'Gujarati'),
    ('ht', 'Haitian Creole'),
    ('iw', 'Hebrew'),
    ('hu', 'Hungarian'),
    ('is', 'Icelandic'),
    ('id', 'Indonesian'),
    ('iu', 'Inuktitut'),
    ('ga', 'Irish'),
    ('it', 'Italian'),
    ('ja', 'Japanese'),
    ('kn', 'Kannada'),
    ('kk', 'Kazakh'),
    ('km', 'Khmer'),
    ('ko', 'Korean'),
    ('ku', 'Kurdish'),
    ('ky', 'Kyrgyz'),
    ('lo', 'Lao'),
    ('la', 'Latin'),
    ('lv', 'Latvian'),
    ('lt', 'Lithuanian'),
    ('lb', 'Luxembourgish'),
    ('mk', 'Macedonian'),
    ('ms', 'Malay'),
    ('ml', 'Malayam'),
    ('mt', 'Maltese'),
    ('mi', 'Maori'),
    ('mr', 'Marathi'),
    ('mn', 'Mongolian'),
    ('ne', 'Nepali'),
    ('no', 'Norwegian'),
    ('oc', 'Occitan'),
    ('or', 'Oriya'),
    ('ps', 'Pashto'),
    ('fa', 'Persian'),
    ('pl', 'Polish'),
    ('pt', 'Portuguese'),
    ('pt-PT', 'Portuguese - Portugal'),
    ('pa', 'Punjabi'),
    ('qu', 'Quechua'),
    ('ro', 'Romanian'),
    ('ru', 'Russian'),
    ('sa', 'Sanskrit'),
    ('gd', 'Scots Gaelic'),
    ('sr', 'Serbian'),
    ('sd', 'Sindhi'),
    ('si', 'Sinhalese'),
    ('sk', 'Slovak'),
    ('sl', 'Slovenian'),
    ('es', 'Spanish'),
    ('su', 'Sundanese'),
    ('sw', 'Swahili'),
    ('sv', 'Swedish'),
    ('syr', 'Syriac'),
    ('tg', 'Tajik'),
    ('ta', 'Tamil'),
    ('tt', 'Tatar'),
    ('te', 'Telegu'),
    ('th', 'Thai'),
    ('bo', 'Tibetan'),
    ('to', 'Tonga'),
    ('tr', 'Turkish'),
    ('uk', 'Ukranian'),
    ('ur', 'Urdu'),
    ('uz', 'Uzbek'),
    ('ug', 'Uighur'),
    ('vi', 'Vietnamese'),
    ('cy', 'Welsh'),
    ('yi', 'Yiddish'),
    ('yo', 'Yoruba'),
    ('', 'Unknown'),
    )


class ActiveTranslationManager(models.Manager):
    def get_query_set(self):
        """
        Return all the active translations. Currently a dummy manager.
        """
        return super(ActiveTranslationManager, self).get_query_set().filter(is_active=True)

class Translation(models.Model):

    class Meta:
        db_table="community_translation"

    # Core properties
    translation = models.TextField()
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES)
    field = models.CharField(max_length=255)
    translation_set = models.CharField(max_length=64, editable=False, blank=True, null=True)

    # Google properties
    from_google = models.BooleanField(default=False)

    # An implementation of a Generic Foreign Key (see Django's contenttypes framework)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    object = generic.GenericForeignKey()

    # Active vs. inactive - useful if humans are overwriting translations
    is_active = models.BooleanField(default=True, editable=False)

    # Creator and modifier - useful if humans are making translations.
    # If Google is translating, created_by is null.
    created_by = models.ForeignKey(User, editable=False, related_name='%(class)s_created_by', null=True, blank=True)
    created_at = models.DateTimeField(editable=False)
    last_modified_by = models.ForeignKey(User, editable=False, related_name='%(class)s_last_modified_by', null=True, blank=True)
    last_modified_at = models.DateTimeField(editable=False)

    objects = models.Manager()
    active = ActiveTranslationManager()

    def save(self, force_insert=False, force_update=False):
        if not self.pk:
            self.created_at = datetime.now()
        self.last_modified_at = datetime.now()
        super(Translation, self).save(force_insert, force_update)

class TranslatedItem(models.Model):

    class Meta:
        abstract = True

    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES)

    def get_translated_fields(self):
        """ Returns a list of translated fields; for example ['title', 'text'] """
        raise NotImplementedError("translated_fields() not yet implemented.")

    translated_fields = property(get_translated_fields)
    translation_id = models.CharField(max_length=64, editable=False, blank=True, null=True)

    translations = generic.GenericRelation(Translation)

    #def translation_creator(self, field="text", to_language=None):
    #    if not to_language:
    #        to_language = translation.get_language()
    #    try:
    #        return self.translations.filter(field=field, language=to_language)[0].created_by
    #    except:
    #        return "No Translator"

    def translated_by_google(self, field="text",to_language=None):
        if not to_language:
            to_language = translation.get_language()
        return self.translations.get(field=field, language=to_language).from_google

    def google_translation_date(self, field="text", to_language=None):
        if not to_language:
            to_language = translation.get_language()
        try:
            return self.translations.get(field=field, language=to_language, from_google=True).created_at
        except:
            return "No Translation Date"

    def has_translation(self, field="text", to_language=None):
        if not to_language:
            to_language = translation.get_language()
        translation_count = self.translations.filter(field=field, language=to_language).count()
        if translation_count is 0:
            return False
        return True

