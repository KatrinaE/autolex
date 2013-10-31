from translate.models import Translation
from community.models import Language, Node

#########################
### TRANSLATION VIEWS ###
#########################


def get_node_with_privileges(user, node_name,community):
    if is_moderator(user, community):
        node = Node.objects.get(slug__iexact=node_name)
    else:
        node = Node.active.get(slug__iexact=node_name)

    # FIXME!!
    #make sure the community ids in the request match the db
    leaf = node.as_leaf_node()
    #if leaf.get_community_id() == community.id:
    userprofile = user.get_profile()
    Translation.update_all_translations(leaf, userprofile.ip)
    return node

def translator(user):
    if user:
        return user.groups.filter(name='translators').count() == 0
    return False

#@login_required
#@django.contrib.auth.decorators.user_passes_test(translator, login_url=reverse('signin'))
def approve_translations(request, context={}):
    translations_dict = {}
    for l in Language.objects.filter(language_code__in=map(first,settings.LANGUAGES)):
        translations_dict[l] = Translation.objects.filter(field='title', is_active=False, language=l)
    context.update({
            'translations_dict' : translations_dict
            })
    return render_to_response('translation/approve_translations.html',
                              context,
                              request)

def translation_detail(request, group_id, context={}):
    try:
        t_title = Translation.objects.get(group_id=group_id, field="title")
        t_text = Translation.objects.get(group_id=group_id, field="text")
        object = t_title.object
        tg_title = Translation.objects.get(content_type=object.content_type.id, object_id=object.id,language=t_title.language, from_google=True, field="title")
        tg_text = Translation.objects.get(content_type=object.content_type.id, object_id=object.id,language=t_title.language, from_google=True, field="text")
    except Translation.DoesNotExist:
        log.error("Translation not found")
        raise Http404
    except Node.DoesNotExist:
        log.error("No object with id '%n' found", t_title.object_id)
        raise Http404

    if request.method == 'POST':
        if request.POST['submit'] == 'Approve':
            t_title.is_active = True
            t_title.save()
            t_text.is_active = True
            t_text.save()
            tg_title.delete()
            tg_text.delete()
        elif request.POST['submit'] == 'Reject':
            t_title.delete()
            t_text.delete()
        return HttpResponseRedirect(reverse('community-home', args=[object.top_ancestor.slug]))

    context.update({
            'title' : t_title.translation,
            'text' : t_text.translation,
            'title_google' : tg_title.translation,
            'text_google' : tg_text.translation,
            'object' : object,
            })

    return render_to_response('translation/translation_detail.html',
                              context,
                              request)

@in_community
@tou_required
def node_translate(request, community_name, node_name, context={}):
    try:
        community = Community.objects.get(slug__iexact=community_name)
        node = get_node_with_privileges(request.user, node_name, community)
        leaf = node.as_leaf_node()
    except (Node.DoesNotExist, Community.DoesNotExist):
        # TODO: Provide a more helpful error message
        log.error('No node with name "%s" found in community "%s"', node_name, community_name)
        raise Http404
    if request.method == 'POST':
        translation_form = TranslationForm(request.POST)
        if translation_form.is_valid():
            group_id = uuid.uuid4()
            t_title = Translation.objects.create(object=leaf,
                                                 field='title', language=translation_form.cleaned_data['language'], from_google=False,
                                                 translation=translation_form.cleaned_data['title'], is_active=False, group_id=group_id)
            t_title.save()
            t_text = Translation.objects.create(object=leaf,
                                                field='text', language=translation_form.cleaned_data['language'], from_google=False,
                                                translation=translation_form.cleaned_data['text'], is_active=False, group_id=group_id)
            t_text.save()

                # Send an email to our moderators
            metrics.object('node', 'translate', node)
                # Success.  Go back to this Object's detail page.
            return HttpResponseRedirect(leaf.get_absolute_url())
        else:
            log.info("Error: Form validation failed: " +
                     translation_form.errors.__unicode__())
            metrics.error('discussion', 'translate', 'Form validation ' \
                              'failed: ' + translation_form.errors.__unicode__())
    else:
        translation_form = TranslationForm()
       # Log page view
        log_content_pageview(request,node)

        context.update({
                'object' : leaf,
                'community' : community,
                'can_edit' : is_editable(request.user, leaf, community),
                'is_moderator' : is_moderator(request.user, community),
                'text' : get_text_for_web(leaf, request.user),
                'must_login_before_viewing' : leaf.members_only and request.user.is_anonymous(),
                'form' : translation_form
                })

        return render_to_response('translation/translate.html',
                                 context,
                                 request)

