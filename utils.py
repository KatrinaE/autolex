import socket
import htmllib
from datetime import timedelta

from django.utils import translation
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.contenttypes.models import ContentType
import ghdlog
log = ghdlog.get_default_logger('apps.translate.utils')
from autolex.models import *

"""
def make_translation(object, ip_address):
"""
"""
    Updates the translation of a single field

    ** Input Parameters **
    object: an object with translated fields
    ip_address: the IP address of the current user. Needed to contact Google Translate.

    ** Modifications **
    Creates new translations in the database (through fetch_google_translation) if necessary.

    ** Output Parameters **
    None

    ** Algorithm **

    Query the database for all translations that match this object and language.
    For each translated field in the object:
            - If there is no translation, call fetch_google_translation to make one.
            - If there is an existing translation, do nothing.
"""
"""
    # Determine which language to translate into.
    to_language = translation.get_language()

    # Look for existing translations in the database for this object in this language.
    content_type = ContentType.objects.get_for_model(object)
    existing_translations = list(Translation.active.filter(content_type=content_type, object_id=object.id,
                                        language=to_language))

    # Generate a new translation set id to link any new translations.
    translation_set = uuid.uuid4()

    # Check to see if there is a translation for each of the object's translated fields.
    # If any field does not have a translation, get one from Google Translate.
    object_id = object.id
    for field in object.translated_fields:
        translations_for_this_field = filter(lambda x:x.field==field, existing_translations)
        if translations_for_this_field == []:
            fetch_google_translation(object, field, to_language, ip_address, translation_set)

    return
"""

def make_translations(object_list, ip_address, to_language=None):
    """
    Bulk translation-updating function. Used with feeds to avoid overloading the database.

    ** Input parameters **
    object_list: a dictionary of the form { objects = [], ids = [], content_types = [] }
    ip_address: the current user's IP address. Needed to contact Google.

    ** Modifications **
    Adds new translation objects to the database through fetch_google_translation.

    ** Output parameters **
    None

    ** Algorithm **

    - Query the database to see if there are pre-existing translations for any of the objects.
    - Determine which objects do not already have translations.
    - Get and save Google translations for those objects using fetch_google_translation.

    """

    # Check that ip address is valid. If not, return without further processing.
    try:
        socket.inet_pton(socket.AF_INET, ip_address)
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ip_address)
        except socket.error:
            return
    # Determine which language to translate into
    if not to_language:
        to_language = translation.get_language()

    # existing_translations will hold all relevant translations already in the database.
    existing_translations = []

    # Get pre-existing translations using a common identifier for differentiating
    # between translated items.
    if settings.COMMON_IDENTIFIER:
        ids_list = []
        for obj in object_list:
            ids_list.append(obj.__getattribute__(settings.COMMON_IDENTIFIER))
        existing_translations = Translation.active.filter(object_id__in=ids_list, language=to_language)

        # Determine which translations are missing and fetch them if necessary.
        for object in object_list:
            if object.language != to_language:
                translation_set = uuid.uuid4()
                for field in object.translated_fields:
                    translation_for_this_field = filter(lambda x: x.object_id == object.node_ptr_id and
                                                        x.field == field,
                                                        existing_translations)
                    if translation_for_this_field == []:
                    # do not get a translation if this field is empty
                        if object.__getattribute__(field) is not '':
                            fetch_google_translation(object, field, to_language, ip_address, translation_set)
        return

    else:
        # Get pre-existing translations using Django's content type framework
        # for differentiating between translated items

        # The items dictionary is used to sort the object list by content type.
        # items will look like { <Content Type 1> : 1, 2, 3 ; <Content Type 2> : 4, 5, 6 }
        # where the numbers are the object ids associated with a given content type.
        items = {}

        # Populate the items dictionary as described above:
        # Add all of the content types represented by objects in object_list
        # as keys to the items dictionary, and all of the object ids as values.
        for object in object_list:
            objects_content_type = ContentType.objects.get_for_model(object)
            if objects_content_type not in items.keys():
                items[objects_content_type] = []
            items[objects_content_type].append(object.id)

        # Get a list of translations connected to the objects in list
        # by querying the database once for each content type.
        for content_type in items.keys():
            existing_translations.extend(Translation.active.filter(object_id__in=items[content_type],
                                                                    content_type=content_type,
                                                                    language=to_language))

        # Create translations for objects that do not have them yet,
        # field by field.
        for object in object_list:
            if object.language != to_language:
                translation_set = uuid.uuid4()
                for field in object.translated_fields:
                    content_type = ContentType.objects.get_for_model(object)
                    translation_for_this_field = filter(lambda x: x.content_type == content_type and
                                                        x.object_id == object.id and
                                                        x.field == field,
                                                        existing_translations)
                    if translation_for_this_field == []:
                        if object.__getattribute__(field) is not '':
                            fetch_google_translation(object, field, to_language, ip_address, translation_set)

    return


GOOGLE_TRANSLATE_ERRORS = [] # a list of errors in the form [{ 'error' : code, 'time' : datetime object}]
GOOGLE_TRANSLATE_ON = settings.ENABLE_GOOGLE_TRANSLATE # initialize to value in settings

def check_google_translate_errors():
    """
    Checks how many errors have been requested by recent requests to Google Translate.
    Disables communication with Google if the number of errors reaches any of the following thresholds:
         - 10 or more errors within 5 minutes
         - 20 or more errors within 1 hour
         - 50 or more errors within 1 day
    """

    global GOOGLE_TRANSLATE_ERRORS
    global GOOGLE_TRANSLATE_ON
    if len(GOOGLE_TRANSLATE_ERRORS) >= 5 and GOOGLE_TRANSLATE_ERRORS[-1]['time'] - GOOGLE_TRANSLATE_ERRORS[-5]['time'] < timedelta(minutes=5):
        # If at least 5 errors have been generated in the last 5 minutes, turn translations off.
        # TO DO send an error message containing the contents of the registry
        GOOGLE_TRANSLATE_ON = False
        return

    if len(GOOGLE_TRANSLATE_ERRORS) >= 20 and GOOGLE_TRANSLATE_ERRORS[-1]['time'] - GOOGLE_TRANSLATE_ERRORS[-20]['time'] < timedelta(hours=1):
        # If at least 20 errors have been generated in the last hour, turn translations off.
        GOOGLE_TRANSLATE_ON = False
        return

    if len(GOOGLE_TRANSLATE_ERRORS) >= 50 and GOOGLE_TRANSLATE_ERRORS[-1]['time'] - GOOGLE_TRANSLATE_ERRORS[-50]['time'] < timedelta(days=1):
        # If at least 50 errors have been generated in the last day, turn translations off.
        GOOGLE_TRANSLATE_ON = False
        return


def communicate_with_google(object, text, to_language, ip_address):
        # Construct the appropriate URL for querying the Google Translate API
        # The URL includes the text to translate [urllib.quote(c)], the object's
        # original language [object.language], the desired translation
        # language [to_language], our API key [settings.GOOGLE_API_KEY],
        # and the user's IP address [ip_address].
        url = 'https://www.googleapis.com/language/translate/v2'
        params = urllib.urlencode({'key' : settings.GOOGLE_API_KEY, \
                                       'q': text, \
                                       'target': to_language, \
                                       'userip' : ip_address, \
                                       'prettyprint' : 'true' \
                                       })
        headers = { 'Referer': settings.ROOT_URL , 'X-HTTP-Method-Override': 'GET' }
        # Create a request from the URL, with a header noting this site as the referer
        request = urllib2.Request(url, params, headers)

        # Ask Google for a response
        try:
            response = urllib2.urlopen(request)
        except urllib2.URLError, e:
            global GOOGLE_TRANSLATE_ERRORS
            # If there is an error code, Google is rejecting the request.
            # Typical error is 400 ("bad request")
            if hasattr(e, 'code'):

                GOOGLE_TRANSLATE_ERRORS.append({'error' : e.code, 'time' : datetime.now()})
                log.error("HTTP %s: Fetching %s Google translation of object '%s' failed." \
                              % (e.code, to_language, object.__unicode__()))
                raise urllib2.URLError(e.code)

            # If there is some other URLError, log and notify.
            elif hasattr(e, 'reason'):
                GOOGLE_TRANSLATE_ERRORS.append({'error' : e.reason, 'time' : datetime.now()})
                log.error("HTTP %s: Fetching %s Google translation of object '%s' failed." \
                              % (e.reason, to_language, object.__unicode__()))
                raise urllib2.URLError(e.reason)

        except:
            # A general error
            GOOGLE_TRANSLATE_ERRORS.append({'error' : e, 'time' : datetime.now()})
            log.error("URLError: Fetching %s Google translation of object '%s' failed." \
                          % (to_language, object.__unicode__()))
            raise Exception

        # If a successful response was obtained...
        else:
            # Process the JSON string.
            results = simplejson.load(response)
            return results['data']['translations'][0]['translatedText']


def break_into_chunks(string,chunks=[],length_of_chunk=5000):
    if len(string) <= length_of_chunk:
        chunks.append(string)
        return chunks
    if len(string) > length_of_chunk:
        try:
            # try to split on a period
            char_to_split_on=string[:length_of_chunk].rindex(".")+1
        except ValueError:
            # no periods
            char_to_split_on=length_of_chunk
        chunks.append(string[:char_to_split_on])
        string=string[char_to_split_on:]
        return break_into_chunks(string,chunks,length_of_chunk)

def fetch_google_translation(object, field_name, to_language, ip_address, translation_set=None):
    """
    Gets a new Google translation of a text string according the following algorithm.

    0. Make sure use of the Google Translate API is activated.  If not, stop and return None.

    1. Split the string into chunks to send to Google, and store those untranslated chunks in a list.
    Google will only accept HTTP requests less than 5,000 characters long, as per their Terms of Service.
    Here, we split each string into 2,500-character chunks so that
    (length of the text) + (length of the rest of the request) stay under that limit.

    2. Create a list, translation_list, for storing the translated chunks.

    3. Send each chunk to Google for translation.
    If Google comes back with a successful translation, add that translated chunk to translation_list
    If the Google request times out or is unsuccessful, return None

    4. Join the chunks in translation_list into one long string, translated_text.

    5. If we already have a Translation object (i.e. we are updating an expired Google translation), overwrite
    its 'translation' field with the new translation.and save it.

    6. If we do not have a Translation object (i.e. this is the first time this item has been translated
    into this language), create a new one and save it.

    7. Return the translation.
    """


    # If we have disabled Google Translate (for example, because Google started rejecting our requests,
    # or because it is turned off in settings.py) return without doing anything.
    global GOOGLE_TRANSLATE_ON
    if not GOOGLE_TRANSLATE_ON:
        return

    # Get the appropriate text and encode it properly - Google will not accept unicode.
    text_to_translate = object.__getattribute__(field_name).encode('utf-8').replace("\n","<br>")

    # Break each string into a chunk short enough to comply with Google's character limit.
    # Returns a list of the form [ "first chunk", "second chunk", "etc." ]. Breaks approximately
    # every 5000 characters (Google's max query length for POST requests) and always on a period if possible.
    chunks=[]

    # Break the text into chunks
    all_chunks=break_into_chunks(text_to_translate)

    # Create a list for storing the translated chunks
    translated_chunks = []
    # Send each chunk to Google for translation
    for c in all_chunks:
        try:
            translated_chunks.append(communicate_with_google(object, c, to_language, ip_address))
        except:
            return

    # All chunks were translated successfully!
    # Join them back together into a string
    translated_text = ''.join(translated_chunks)
    translated_text=translated_text.replace('<br>','***fakelinebreak***')

    # Unescape HTML characters [i.e. convert &quot; to "]
    # Snippet from http://wiki.python.org/moin/EscapingHtml

    def unescape(s):
        p = htmllib.HTMLParser(None)
        p.save_bgn()
        p.feed(s)
        return p.save_end()

    translated_text=unescape(translated_text)
    translated_text=translated_text.replace("***fakelinebreak***","\n")


    # Create a new translation object.
    if settings.COMMON_IDENTIFIER:
        id = object.__getattribute__(settings.COMMON_IDENTIFIER)
    else:
        id = object.id
    content_type = ContentType.objects.get_for_model(object)
    t = Translation.active.create(content_type=content_type, object_id=id,
                                   field=field_name, language=to_language, from_google=True,
                                   translation=translated_text, translation_set=translation_set)
    t.save()
    return


def get_translated_version(object, field_name, to_language=None):
    """
    Used for displaying the translated version of a particular field.

    ** Input Parameters **
    object: an object containing translated fields
    field_name: the particular field in the object whose translation we want.

    ** Modifications **
    None

    ** Output Parameters **
    A string containing the translated text. Falls back to the original text
    if no translation is found.

    ** Algorithm **

    0. Get the desired language for display.

    1. If the desired language matches the object's language, we don't need
       a translation - return the original text.

    2. Look in the database for a translation. If there is one, return it.

    3. If there is no translation, return the original text.

    """

    if field_name not in object.translated_fields:
        raise ValueError("This field is not marked for translation")

    if not to_language:
        to_language = translation.get_language()

    if to_language == object.language:
        return object.__getattribute__(field_name)
    try:
        # Look for a translation in the database.
        # If one is found, return it.
        if settings.COMMON_IDENTIFIER:
            id = object.__getattribute__(settings.COMMON_IDENTIFIER)
            t = Translation.active.get(object_id=id, field=field_name, language=to_language)
        else:
            content_type = ContentType.objects.get_for_model(object)
            t = Translation.active.get(object_id=object.id, content_type=content_type,
                                        field=field_name,language=to_language)
        return t.translation
    except (Translation.DoesNotExist, AttributeError):
        # If there is no translation, fall back on the original text.
        return object.__getattribute__(field_name)
    except MultipleObjectsReturned:
        # If there is more than one translation, log an error (there should only be one active translation).
        # Get the most recent translation
        log.error("Error: Multiple translations returned for the %s field object '%s' in language %s" \
                      % (field_name, object.__unicode__(), to_language,))
        return Translation.active.filter(object_id=object.id, content_type=content_type,
                                        field=field_name,language=to_language).order_by("-last_modified_at")[0].translation

def translation_from_google(object):
    """ Returns True if an object's desired translation is from Google, False if it is not."""
    to_language = translation.get_language()
        # Get the desired translation from the database.
    content_type = ContentType.objects.get_for_model(object)
    t = Translation.active.get(content_type=content_type, object_id=object.id,
                               field='text', language=to_language)
    return t.from_google

