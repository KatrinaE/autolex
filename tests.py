
# coding: utf-8

import re
import urllib2
import datetime

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from autolex.models import Translation, TranslatedItem
from autolex.detection import LangDetect
from autolex.utils import make_translations, fetch_google_translation, break_into_chunks, communicate_with_google, get_translated_version, check_google_translate_errors
import autolex.utils as autolex_utils

def suite():
    #suite = unittest.TestLoader().loadTestsFromTestCase(WidgetTestCase)
    return suite

class TestRegularItem(models.Model):
    """ Test class for non-translated items """
    id = models.AutoField(primary_key=True)
    text1 = models.TextField()

    next_id = 1
    def __init__(self, text1="Text in this object will never be translated."):
        self.id = self.next_id
        self.__class__.next_id += 1
        self.text1 = text1

    def __unicode__(self):
        return "Test RegularItem"

class TestTranslatedItem(TranslatedItem):
    """ Test class for creating items that will be translated """
    id = models.AutoField(primary_key=True)
    text1 = models.TextField()
    text2 = models.TextField()
    untranslated_field = models.TextField()

    next_id = 1

    def get_translated_fields(self):
        return ['text1', 'text2']

    translated_fields = property(get_translated_fields)

    def __init__(self, text1, language, text2=None):
        self.id = self.next_id
        self.__class__.next_id += 1
        self.text1 = text1
        self.untranslated_field = "This text will not be translated."
        self.language = language
        self.translation_id = None
        if text2 is not None:
            self.text2 = text2
        else:
            self.text2 = ''

    def __unicode__(self):
        return "Test TranslatedItem"

class autolex_test(TestCase):
    def setUp(self):
        # Patch needed settings
        self.old_common_identifier = settings.COMMON_IDENTIFIER
        settings.COMMON_IDENTIFIER = None

        self.user1 = User.objects.create_user('__test_user__', '')
        self.user1.first_name = '__test__'
        self.user1.last_name = '__user__'
        self.user1.save()

        self.object1 = TestTranslatedItem("This is some English example text.", 'en')
        self.object1.save()
        self.testtranslateditem_type = ContentType.objects.get_for_model(TestTranslatedItem)
        self.object1_translation = Translation.objects.create(translation="spanish foo", language='es', field='text1',
                                                              content_type=self.testtranslateditem_type, object_id=self.object1.id)
        self.test_ip = "134.174.191.73"

    # Util function for comparing desired strings to output strings using regex
    def assert_re_count(self, str_, re_to_find, count, re_flags=None, msg=None):
        """ Assert that re_to_find matches oin str_ exactky count times """
        if re_flags is None:
            f = lambda: re.findall(re_to_find, str_)
        else:
            f = lambda: re.findall(re_to_find, str_, re_flags)

        r = f()
        if len(r) != count:
            m = "'%s' matches '%s': %s (and not %i times)" % \
                (str_, re_to_find, r, count)
            if msg:
                m = "%s (%s)" % (m, msg)
            raise self.failureException, m


    ############################################################
    ### Tests that begin with the break_into_chunks function ###
    ############################################################
    def test_break_into_chunks(self):
        """
        Tests that long strings are properly broken up via break_into_chunks.
        """
        # TO DO: make break_into_chunks more sophisticated.
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        one_chunk=break_into_chunks("This is a single-chunk string.", chunks=[])
        self.assertEqual(len(one_chunk), 1)

        two_chunks=break_into_chunks("This is a double-string chunk because it is longer than the character limit, which is " \
                                         "given as the second argument of this function. It will be broken into two chunks " \
                                         "because there are two sentences.", chunks=[], length_of_chunk=150)
        self.assertEqual(len(two_chunks), 2)

        no_periods=break_into_chunks("This is a double-string chunk, but because the first sentence is longer than the " \
                                         "character limit, the break will happen in the middle of the sentence, which will " \
                                         "decrease translation quality. The second chunk contains both periods.", chunks=[], length_of_chunk=150)
        self.assertEqual(len(no_periods), 2)
        self.assert_re_count(no_periods[0], '\.', 0)
        self.assert_re_count(no_periods[1],'\.', 2)


    ###################################################################
    ### Tests that begin with the fetch_google_translation function ###
    ###################################################################
    def test_fetch_google_translation(self):
        """
        Tests that fetch_google_translation retrieves and saves a proper translation
        """
        # 1. create an object to be translated.
        # 2. translate using fetch_google_translation
        # 3. verify that there is a new translation in the database corresponding with
        # that language and object.

        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        test_object = TestTranslatedItem("This is some basic text for the example object.", 'en')
        test_object.save()
        fetch_google_translation(test_object, 'text1', 'es', self.test_ip)

        new_translation = Translation.objects.filter(object_id=test_object.id, content_type=self.testtranslateditem_type,
                                                  field='text1', language='es')
        self.assertEqual(len(new_translation),1)

    def test_too_long(self):
        """
        Tests that sending to Google a string of >5000 characters returns an error.
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        really_long_string = "This is a really long string. " * 500
        really_long_string = really_long_string.encode('utf-8')

        try:
            communicate_with_google(self.object1, really_long_string, 'es', self.test_ip)
        except urllib2.URLError, e:
            self.assertEqual(e.reason, 400)
        else:
            self.fail("Translating a too-long string should have resulted in an error.")

    def test_google_error_registry(self):
        """
        Tests that fetch_google_translate returns immediately if there are too many
        errors in the GOOGLE_TRANSLATE_ERRORS registry
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        recent_error_entry = {'error' : 400, 'time' : datetime.datetime.now() }
        older_error_entry = {'error' : 400, 'time' : datetime.datetime.now() - datetime.timedelta(minutes=55)}
        oldest_error_entry = { 'error' : 400, 'time' : datetime.datetime.now() - datetime.timedelta(hours=23)}

        # too many errors in the last 5 minutes
        self.assertEqual(autolex_utils.GOOGLE_TRANSLATE_ON, True)
        autolex_utils.GOOGLE_TRANSLATE_ERRORS = [recent_error_entry] * 5
        check_google_translate_errors()
        self.assertEqual(autolex_utils.GOOGLE_TRANSLATE_ON, False)

        # too many errors in the last hour
        autolex_utils.GOOGLE_TRANSLATE_ON = True
        autolex_utils.GOOGLE_TRANSLATE_ERRORS = [older_error_entry] * 16
        autolex_utils.GOOGLE_TRANSLATE_ERRORS.extend([recent_error_entry] * 4)
        check_google_translate_errors()
        self.assertEqual(autolex_utils.GOOGLE_TRANSLATE_ON, False)

        # too many errors in the last day
        autolex_utils.GOOGLE_TRANSLATE_ON = True
        autolex_utils.GOOGLE_TRANSLATE_ERRORS = [oldest_error_entry] * 31
        autolex_utils.GOOGLE_TRANSLATE_ERRORS.extend([older_error_entry] * 15)
        autolex_utils.GOOGLE_TRANSLATE_ERRORS.extend([recent_error_entry] * 4)
        check_google_translate_errors()
        self.assertEqual(autolex_utils.GOOGLE_TRANSLATE_ON, False)

        # acceptable number of errors
        autolex_utils.GOOGLE_TRANSLATE_ON = True
        autolex_utils.GOOGLE_TRANSLATE_ERRORS = [oldest_error_entry] * 30
        autolex_utils.GOOGLE_TRANSLATE_ERRORS.extend([older_error_entry] * 15)
        autolex_utils.GOOGLE_TRANSLATE_ERRORS.extend([recent_error_entry] * 4)
        check_google_translate_errors()
        self.assertEqual(autolex_utils.GOOGLE_TRANSLATE_ON, True)


    ############################################################
    ### Tests that begin with the make_translations function ###
    ############################################################
    def test_make_translations(self):
        """
        Tests that make_translations creates proper translations.
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        Translation.objects.all().delete()
        self.object1.text2 = "This is some more sample text."
        self.object1.save()
        make_translations([self.object1], self.test_ip, to_language="es")
        self.assertEqual(Translation.active.count(), 2)
        self.assertEqual(Translation.active.all()[0].translation_set, Translation.active.all()[1].translation_set)
        self.assertEqual(Translation.active.filter(object_id=self.object1.id,
                                                   content_type=self.testtranslateditem_type,
                                                   language='es').count(), 2)

    def test_multiple_languages(self):
        """
        Tests that make_translations does not create translations for objects that
        were originally written in the desired language.
        """

        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        Translation.objects.all().delete()
        self.object_es=TestTranslatedItem("El texto de este objecto era escrito en espanol", 'es')
        self.object_es.save()
        make_translations([self.object1, self.object_es], self.test_ip, to_language="es")
        self.assertEqual(Translation.active.count(), 1)

        # also works when using a common identifier
        settings.COMMON_IDENTIFIER = 'id'
        Translation.objects.all().delete()
        make_translations([self.object1, self.object_es], self.test_ip, to_language="es")
        self.assertEqual(Translation.active.count(), 1)
        settings.COMMON_IDENTIFIER = None

    def test_translate_bad_object(self):
        """
        Tests that make_translations will not work with objects that are not TranslatedItems
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        # create an object that is not a TranslatedItem
        # attempt to translate one of that object's fields.
        # verify that no translation was created
        bad_object = TestRegularItem()
        bad_object.save()
        self.assertRaises(AttributeError, lambda: make_translations([bad_object], self.test_ip, 'es'))

    def test_translate_empty_field(self):
        """
        Tests that using make_translations on an empty field does not create any translation objects.
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        Translation.objects.all().delete()
        make_translations([self.object1],self.test_ip, to_language='es')
        self.assertEqual(Translation.active.count(), 1)

    def test_translate_bad_ip(self):
        """
        Tests that make_translations  does not call Google unless it has a proper IP address
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        Translation.objects.all().delete()
        make_translations([self.object1],"bad.ip", to_language='es')
        self.assertEqual(Translation.active.count(), 0)

    def test_common_identifier(self):
        """
        Tests that marking a field as the common identifier (using settings.COMMON_IDENTIFIER)
        does not disable translation.
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        settings.COMMON_IDENTIFIER = 'id'
        Translation.objects.all().delete()
        make_translations([self.object1], self.test_ip, to_language='es')
        self.assertEqual(Translation.active.count(), 1)
        settings.COMMON_IDENTIFIER = None

    def test_already_translated_field(self):
        """
        Tests that, for an object with two translated fields, one of which is already translated,
        make_translations only makes a translation for the untranslated field.
        """

        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        self.object1.text2 = "New sample text."
        self.object1.save()

        self.assertEqual(Translation.active.count(), 1)
        make_translations([self.object1], self.test_ip, to_language='es')
        self.assertEqual(Translation.objects.count(), 2)
        self.assertEqual(Translation.objects.get(object_id=self.object1.id, content_type=self.testtranslateditem_type,
                                                 language="es", field="text1").translation, self.object1_translation.translation)

    def test_inactive_translation(self):
        """
        Tests that a new translation is made if an old translation exists but is marked inactive.
        """
        if not settings.ENABLE_GOOGLE_TRANSLATE:
            return

        self.object1.text2 = "This is some more sample text. A new translation will be made because the " \
            "relevant translation (created below) is  inactive."
        self.object1.save()
        self.object1_translation2 = Translation.objects.create(object_id=self.object1.id,
                                                               content_type=self.testtranslateditem_type,
                                                               field="text2", language="es",
                                                               translation = "spanish 2 foo",
                                                               is_active=False)
        self.object1_translation2.save()
        self.assertEqual(Translation.objects.count(), 2)
        self.assertEqual(Translation.active.count(), 1)
        make_translations([self.object1], self.test_ip, to_language='es')
        self.assertEqual(Translation.objects.count(), 3)
        self.assertEqual(Translation.active.count(), 2)

    #################################################################
    ### Tests that begin with the get_translated_version function ###
    #################################################################
    def test_get_translated_version(self):
        """
        Tests that get_translated_version retrieves a proper translation.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        translated_version = get_translated_version(self.object1, "text1", 'es')
        self.assertEqual(translated_version, self.object1_translation.translation)

    def test_get_no_translation(self):
        """
        Tests that get_translated_version falls back on the original text if
        there is no appropriate translation object in the database.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        translated_version = get_translated_version(self.object1, "text1", 'fr')
        self.assertEqual(translated_version, self.object1.text1)

    def test_get_two_translations(self):
        """
        Tests that get_translated_version returns the most recent active translation.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        second_translation = Translation.objects.create(object_id=self.object1.id,
                                                        content_type=self.testtranslateditem_type,
                                                        field="text1", language='es',
                                                        translation="spanish bar")
        second_translation.save()
        translated_version = get_translated_version(self.object1, "text1", 'es')
        self.assertEqual(translated_version, second_translation.translation)

    def test_get_inactive_translation(self):
        """
        Tests that get_translated_version falls back on the original text if
        the matching translation is marked inactive.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        self.object1.text2 = "This is some more sample text. It should not be translated because the " \
            "relevant translation (created below) is  inactive."
        self.object1.save()
        self.object1_translation2 = Translation.objects.create(object_id=self.object1.id,
                                                               content_type=self.testtranslateditem_type,
                                                               field="text2", language="es",
                                                               translation = "spanish 2 foo",
                                                               is_active=False)
        self.object1_translation2.save()
        fallback_version = get_translated_version(self.object1, "text2", 'es')
        self.assertEqual(fallback_version, self.object1.text2)

    def test_get_common_identifier(self):
        """
        Tests that get_translated_version works correctly with a common identifier.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        settings.COMMON_IDENTIFIER = 'id'
        translated_version = get_translated_version(self.object1, "text1", 'es')
        self.assertEqual(translated_version, self.object1_translation.translation)
        settings.COMMON_IDENTIFIER = None


    def test_get_bad_field(self):
        """
        Tests that using get_translated_version with a non-translated field raises an error.
        """
        if not settings.ENABLE_TRANSLATIONS:
            return

        self.assertRaises(ValueError, lambda: get_translated_version(self.object1, "untranslated_field", 'es'))

    def test_detection(self):
        """
        Tests that autolex.detection correctly detects a string's language.
        """

        if not settings.ENABLE_TRANSLATIONS:
            return

        text_nl = "De snelle bruine vos springt over de luie hond"
        text_en = "The quick brown fox jumps over the lazy dog"
        text_fr = "Le renard brun rapide saute par-dessus le chien paresseux"
        text_de = "Der schnelle braune Fuchs springt Å¸den faulen Hund."
        text_es = "El rÅ·pido zorro marrÅÛn salta sobre el perro perezoso"
        text_ru = "úÙ®≤ úÙ®ÁúÙ®–úÙ®ÈúÙ®–úÙ®Â úÙ®ÓúÙ®”úÙ®– úÙ®÷úÙ®ÿúÙ®€ úÙ®—úÙ®Î úÙ®ÊúÙ®ÿúÙ®‚úÙ®‡úÙ®„úÙ®·? úÙ®¥úÙ®–, úÙ®›úÙ®ﬁ úÙ®‰úÙ®–úÙ®€úÙ®ÏúÙ®ËúÙ®ÿúÙ®“úÙ®ÎúÙ®Ÿ úÙ®ÌúÙ®⁄úÙ®◊úÙ®’úÙ®‹úÙ®ﬂúÙ®€úÙ®ÔúÙ®‡!"

        ld=LangDetect()
        self.assertEqual(ld.detect(text_nl), "nl")
        self.assertEqual(ld.detect(text_en), "en")
        self.assertEqual(ld.detect(text_fr), "fr")
        self.assertEqual(ld.detect(text_de), "de")
        self.assertEqual(ld.detect(text_es), "es")
        self.assertEqual(ld.detect(text_ru), "ru")

    def tearDown(self):
        settings.COMMON_IDENTIFIER = self.old_common_identifier
