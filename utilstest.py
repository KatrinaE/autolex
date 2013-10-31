from django.utils import translation
from django.core.exceptions import MultipleObjectsReturned
import ghdlog
log = ghdlog.get_default_logger('apps.translate.utils')

from translate.models import *


#def current_language():
#    """ Returns the Language object associated with the current user's language code """
#        # Get the language code from Django's translation module
#    to_language_code = translation.get_language()
#    try:
#        # Look for the language object that matches this language code
#        return Language.objects.get(language_code=to_language_code)
#    except Language.DoesNotExist:
        # If there is no language that matches this code, fall back on the default.
#        return Language.objects.get(language_code=settings.LANGUAGE_CODE)
#    except MultipleObjectsReturned:
        # If multiple languages match this code, there is a problem with our
        # data.  Fall back on the default and log an error.
        # TO DO: Log an error.
#        return Language.objects.get(language_code=settings.LANGUAGE_CODE)

def translation_from_google(object):
    """ Returns True if an object's desired translation is from Google, False if it is not."""
    to_language = translation.get_language()
        # Get the desired translation from the database.
    t = Translation.objects.get(content_type=object.content_type, object_id=object.id,
                               field='text', language=to_language)
    return t.from_google

def translation_author(object):
    """ Returns the (human) author of a translation"""
    to_language = translation.get_language()
    try:
        t = Translation.objects.get(content_type=object.content_type, object_id=object.id,
                                   field='text', language=to_language)
        return t.get_author()
    except (Translation.DoesNotExist, MultipleObjectsReturned):
        return None

def get_translated_version(object, field_name):
    """
    Used for displaying the translated version of a particular field.

    ** Input Parameters **
    object: an object containing translated fields
    field_name: the particular field in the object whose translation we want.

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

    if settings.LOOKUP_TO_LANGUAGE_DISPLAY:
        to_language = translation.get_language()
    else:
        to_language = object.language
    if to_language == object.language:
        return object.__getattribute__(field_name)
    if settings.LOOKUP_IN_DATABASE_FOR_DISPLAY:
        try:
            # Look for a translation in the database.
            # If one is found, return it.
            t = Translation.objects.get(object_id=object.id, content_type=object.content_type,
                                        field=field_name,language=to_language)
            return t.translation
        except (Translation.DoesNotExist, AttributeError):
            # If there is no translation, fall back on the original text.
            return object.__getattribute__(field_name)
        except MultipleObjectsReturned:
            # Log an error - there should only be one active translation.
            log.error("Error: Multiple translations returned for the %s field object '%s' in language %s" \
                      % (field_name, object.__unicode__(), to_language,))
            return object.__getattribute__(field_name)
    else:
        return "Dummy translation string"

def update_in_bulk(object_list, ip_address):
    """
    Bulk translation-updating function. Used with feeds to avoid overloading the database.

    ** Input parameters **
    object_dict: a dictionary of the form { objects = [], ids = [], content_types = [] }
    objects: the objects whose translations we want
    ids: the objects' ids
    content_types: the objects' content types
    ip_address: the current user's IP address. Needed to contact Google.

    ** Output parameters **
    None

    For any object in our dictionary, there are four possibilities:
    a. We already have a human-provided translation, which will not need any updating.
    b. We have a Google translation that is less than 14 days old, which will not need any updating.
    c. We have a Google translation that is 14 days or older, and will need to update it.
    d. We do not have any translation for this object, and will need to create one.
    We address all 4 of these possibilites.

    ** Algorithm **

    1. Query the database to see if we already have translations for any of the objects.
    Store those translations in a list, t_list.

    2. Filter Google translations from t_list and check whether or not they are expired.

    3. Update expired Google translations using fetch_google_translation.

    4. Determine which objects do not already have translations by comparing the object_ids
    of the translations in t_list to the ids in object_dict['ids'].

    5. Get and save Google translations for those objects using fetch_google_translation.

    """
    if settings.ENABLE_TRANSLATIONS:
        items = {}
        t_list = []

        for object in object_list:
            if object.content_type not in items.keys():
                items[object.content_type] = []
            items[object.content_type].append(object.id)

    if settings.LOOKUP_TO_LANGUAGE_UPDATE:
        to_language = translation.get_language()

    # Get a list of active translations connected to the objects in object_dict.
    if settings.LOOKUP_IN_DATABASE_FOR_UPDATE:
        for content_type in items.keys():
            t_list.extend(Translation.objects.filter(object_id__in=items[content_type],
                                                     content_type=content_type,
                                                     language=to_language))
    # Check which of these translations are from Google.
    # Avoids using filter(from_google=True) on the original queryset so that the database
    # is only hit once, when evaluating t_list. If we used filter() here, then the database would
    # be hit again when t_from_google was evaluated.
    if settings.MAKE_TRANSLATION_SET:
        #t_from_google = filter(lambda x:x.from_google==True, t_list)

        # Update expired Google translations. A translation is expired if it has been in our
        # database for 14 days or more.
        #for t in t_from_google:
        #    age = datetime.now() - t.last_modified_at
        #    if age.days >= 14:
        #        fetch_google_translation(object, field_name, to_language,
        #                                 ip_address, translation_object=t,
        #                                 translation_set=translation_set)

    # Create translations for objects that do not have them yet:

        # Create a list of the object_ids connected to the translations in t_list
        t_object_ids = map(lambda x:x.object_id, t_list)
        # Compare the object ids in t_object_ids to the ids in the object dictionary.
        # We compare to object_dict['objects'] and not object_dict['ids'] so that we can use the
        # actual object when we call fetch_google_translation.
        objects_without_translations = filter(lambda x:x.id not in t_object_ids,object_list)
        for object in objects_without_translations:

            # Create a unique identifier to tie together all of the translations
            # we create for this object.
            translation_set = uuid.uuid4()

            # Create a translation for each field that needs to be translated
            for field_name in object.translated_fields():
                fetch_google_translation(object, field_name, to_language,
                                         ip_address, translation_set=translation_set)
    return

def update_translated_fields(object, ip_address, to_language=None):
    """
    Updates the translation of a single field

    ** Input Parameters **
    object: an object with translated fields
    field_name: the particular field that needs to be updated; for example, 'title' or 'text'
    ip_address: the IP address of the current user. Needed to contact Google Translate
    translation_set:
    to_language:

    ** Output Parameters **
    None

    ** Algorithm **

    Query the database for all tarnslations that match this object and language, and store them in a list.
    For each translated field in the object:
            2. If there is no translation in the list, ask Google for one.
            3. If there is a translation in the list, check to see if it is from Google. If it is from Google
            and is older than Google's 14 days, ask Google for a new one.

    """

    if settings.LOOKUP_TO_LANGUAGE_UPDATE:
        if not to_language:
            # If we don't already know which language we want to update this translation for, find out
            to_language = translation.get_language()
    # Look for an existing translation in the database

        # You can store the queryset in memory as a list, but it might have a large memory cost depending on how
        # many items are in the queryset
    if settings.LOOKUP_IN_DATABASE_FOR_UPDATE:
        t = list(Translation.objects.filter(content_type=object.content_type, object_id=object.id,
                                            language=to_language).order_by('last_modified_at'))
    # make a new translation set to store new translations we have to make.
    if settings.MAKE_TRANSLATION_SET:
        translation_set = uuid.uuid4()
        object_id = object.id
        for field in object.translated_fields():
            translations_for_this_field = filter(lambda x:x.field==field and x.object_id==object_id, t)
            if translations_for_this_field == []:
                fetch_google_translation(object, field, to_language, ip_address, translation_set=translation_set)
            #else:
                # If there is a translation in our database, check to see if it is from Google.
                # If it is from Google and is older than Google's 15-day limit on storing results,
                # ask Google for a new one.

                # If there is more than one object, just use the first one.

                # The existing translation object is included in the call to fetch_google_translate
                # so that it can be overwritten and saved; a new object will not be created.
                #old_translation = translations_for_this_field[0]
                #if old_translation.from_google == True:
                #    age = datetime.now() - old_translation.last_modified_at
                #    if age.days >= 14:
                #        fetch_google_translation(object, field, to_language, ip_address, translation_object=old_translation, translation_set=translation_set)

    #translation_cache = "_" + field_name + "_cache"
    #setattr(object, translation_cache, t.translation)
    return

def fetch_google_translation(object, field_name, to_language, ip_address, translation_object=None, translation_set=None):
    """
    Gets a new Google translation of a text string according the following algorithm.

    0. Make sure use of the Google Translate API is activated.  If not, stop and return None.

    1. Split the string into chunks to send to Google, and store those untranslated chunks in a list.
    Google will only accept HTTP requests less than 5,000 characters long, as per their Terms of Service.
    Here, we split each string into 2,500-character chunks so that
    (length of the text) + (length of the rest of the request) stay under that limit.
    v
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

    # If we have disabled Google Translate (for example, because Google started rejecting our requests),
    # return without doing anything.
    if not settings.ENABLE_GOOGLE_TRANSLATE:
        return

    # Get the appropriate text and encode it properly - Google will not accept unicode.
    text_to_translate = object.__getattribute__(field_name).encode('utf-8')

    # Utility function for keeping the strings we send to Google below Google's character limit
    # Returns a list of the form [ "first 1000 characters", "second 1000 characters", "etc." ]
    def break_into_chunks(t,x=0,chunks=[]):
        if x >= len(t):
            return chunks
        if x < len(t):
            chunks.append(t[x:x+1000])
            x=x+1000
            return break_into_chunks(t,x,chunks)

    # Break the text into chunks
    chunks=break_into_chunks(text_to_translate)

    # Create a list for storing the translated chunks
    translation_list = []

    # Send each chunk to Google for translation
    for c in chunks:

        # Construct the appropriate URL for querying the Google Translate API
        # The URL includes the text to translate [urllib.quote(c)], the object's
        # original language [object.language], the desired translation
        # language [to_language], our API key [settings.GOOGLE_API_KEY],
        # and the user's IP address [ip_address].
        url = ('https://ajax.googleapis.com/ajax/services/language/translate?' +
               'v=1.0&q=' + urllib.quote(c) +
               '&langpair=' + object.language + '%7C' + to_language +
               '&key=' + settings.GOOGLE_API_KEY +
               '&userip=' + ip_address +
               '&type=text' )
        # For Google Translate version 2 - too advanced for us right now,
        # but we should upgrade ASAP because it preserves line breaks.
        # url = ('https://www.googleapis.com/language/translate/' +
        #       'v2?q=' + 'helloworld' + #+ urllib.quote(c) +
        #       '&source=' + 'en' + #self.language.language_code +
        #       '&target=' + 'es' + #to_language.language_code +
        #       '&key=' + settings.GOOGLE_API_KEY +
        #       #'&userip=' + ip_address +
        #       "&prettyprint=true")


        # Create a request from the URL, with a header noting GHDonline as the referer
        request = urllib2.Request(url, None, {'Referer': 'http://www.ghdonline.org'})
        # Ask Google for a response
        if settings.COMMUNICATE_WITH_GOOGLE:
            try:
                response = urllib2.urlopen(request)
            except urllib2.URLError, e:

            # If there is a URLError, log the error and return without updating the translation.
            # Users will see the untranslated version instead.

                try:
                # If the error response code is 400, Google is rejecting our requests.
                # Send an error to our admins and immediately disable translation updates.
                    if e.code == 400:
                    # TO DO: Send the email message
                        log.error("HTTP %s: Fetching %s Google translation of object '%s' failed." \
                                  % (e.code, to_language, object.__unicode__()))
                    # TO DO: Find a better way to do this than changing settings at runtime (evil!!)
                        settings.ENABLE_GOOGLE_TRANSLATE = False

                    # If the error code is 414, the request was too long -
                    # We should decrease the length of each chunk.
                    elif e.code ==414:
                        log.error("HTTP %s: Fetching %s Google translation of object '%s' failed. Decrease length of strings created in break_into_chunks()." \
                                  % (e.code, to_languagee, object.__unicode__()))
                    else:
                        log.error("HTTP %s: Fetching %s Google translation of object '%s' failed." \
                                      % (e.code, to_language, object.__unicode__()))

                except AttributeError:
                # This error does not have the field e.code. Just log a general error.
                    log.error("URLError: Fetching %s Google translation of object '%s' failed." \
                                  % (to_language, object.__unicode__()))

            # If there is an old translation, delete it (since it is expired).
                if translation_object:
                    translation_object.delete()
                return

        # If we received a successful response...
            else:
            # Process the JSON string.
                results = simplejson.load(response)

            # Getting the translation appeared to work. Double-check by ensuring that
            # the response status is 200.  If it is not, log an error and return, as above.
            # TO DO: This check may be redundant
                if results['responseStatus'] is 200:
                    translation_list.append(results['responseData']['translatedText'])
                else:
                    log.error("HTTP %s: Fetching %s Google translation of object '%s' failed." %
                              (results['responseStatus'], to_language, object.__unicode()))
                    if translation_object:
                        translation_object.delete()
                    return
        else:
            translation_list.append("foo")

    # All chunks were translated successfully!
    # Join them back together into a string
    translated_text = ''.join(translation_list)

    # If we already have an old Google translation, just update it - don't make a new one
    if settings.SAVE_TO_DATABASE:
        if translation_object:
            translation_object.translation = translated_text
            translation_object.save()
            return translation_object
        else:
            # If we do not already have an old translation, create a new one
            t = Translation.objects.create(content_type=object.content_type, object_id=object.id,
                                           field=field_name, language=to_language, from_google=True,
                                           translation=translated_text, translation_set=translation_set)
            t.save()
        return t
    else:
        return
