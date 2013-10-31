from django.forms.models import BaseModelFormSet, modelformset_factory, save_instance
from django.forms.formsets import formset_factory
from django.contrib.admin.options import InlineModelAdmin, flatten_fieldsets
from django.db import models
import django.forms as forms
from autolex.models import Translation, LANGUAGE_CHOICES

class TranslationForm(forms.ModelForm):
    # For testing purposes only.  Should not accept this field unless
    # we're in the test suite.
    testing_channel = forms.CharField(required=False)

    model = Translation
    fields = ['language']
    exclude = ['field', 'from_google']#language = forms.ChoiceField(required=True, choices=LANGUAGE_CHOICES, label="Language")
    is_active = forms.ChoiceField(widget=forms.RadioSelect(),required=True, choices=[[True, "Active"], [False, "Inactive"]], label="Status")
    title=forms.CharField(required=True, widget=forms.TextInput, label="Title")
    text = forms.CharField(required=True, widget=forms.Textarea, label="Text")


    # Replace large Textarea field with smaller TextInput field
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'translation':
            request = kwargs.pop("request", None)
            kwargs['widget'] = TextInput
            return db_field.formfield(**kwargs)
        return super(TranslationStackedInline,self).formfield_for_dbfield(db_field, **kwargs)

    def clean(self):
        # Probably want to check that the title field is < 256 characters
        return super(TranslationForm, self).clean()

class BaseTranslationInlineFormSet(BaseModelFormSet):
    """
    A formset for generic inline objects to a parent.
    """

    def __init__(self, data=None, files=None, instance=None, save_as_new=None,
                 prefix=None, queryset=None):
        # Avoid a circular import.
        from django.contrib.contenttypes.models import ContentType
        opts = self.model._meta
        self.instance = instance
        self.rel_name = '-'.join((
            opts.app_label, opts.object_name.lower(),
            self.ct_field.name, self.ct_fk_field.name,
        ))
        if self.instance is None or self.instance.pk is None:
            qs = self.model._default_manager.none()
        else:
            if queryset is None:
                queryset = self.model._default_manager
            qs = queryset.filter(**{
                self.ct_field.name: ContentType.objects.get_for_model(self.instance),
                self.ct_fk_field.name: self.instance.pk,
            })
        super(BaseTranslationInlineFormSet, self).__init__(
            queryset=qs, data=data, files=files,
            prefix=prefix
        )

    #@classmethod
    def get_default_prefix(cls):
        opts = cls.model._meta
        return '-'.join((opts.app_label, opts.object_name.lower(),
                        cls.ct_field.name, cls.ct_fk_field.name,
        ))
    get_default_prefix = classmethod(get_default_prefix)

    def save_new(self, form, commit=True):
        # Avoid a circular import.
        from django.contrib.contenttypes.models import ContentType
        kwargs = {
            self.ct_field.get_attname(): ContentType.objects.get_for_model(self.instance).pk,
            self.ct_fk_field.get_attname(): self.instance.pk,
        }
        new_obj = self.model(**kwargs)
        return save_instance(form, new_obj, commit=commit)

def translation_inlineformset_factory(model, form=TranslationForm,
                                  formset=BaseTranslationInlineFormSet,
                                  ct_field="content_type", fk_field="object_id",
                                  fields=None, exclude=None,
                                  extra=3, can_order=False, can_delete=True,
                                  max_num=0,
                                  formfield_callback=lambda f: f.formfield()):
    """
    Returns a ``TranslationInlineFormSet`` for the given kwargs.

    Based on InlineModelFormSet
    """
    opts = model._meta
    # Avoid a circular import.
    from django.contrib.contenttypes.models import ContentType
    # if there is no field called `ct_field` let the exception propagate
    ct_field = opts.get_field(ct_field)
    if not isinstance(ct_field, models.ForeignKey) or ct_field.rel.to != ContentType:
        raise Exception("fk_name '%s' is not a ForeignKey to ContentType" % ct_field)
    fk_field = opts.get_field(fk_field) # let the exception propagate
    if exclude is not None:
        exclude = list(exclude)
        exclude.extend([ct_field.name, fk_field.name])
    else:
        exclude = [ct_field.name, fk_field.name, 'field', 'translation', ]
        FormSet = modelformset_factory(model, form=form,
                                   formfield_callback=formfield_callback,
                                   formset=formset,
                                   extra=extra, can_delete=can_delete, can_order=can_order,
                                   fields=fields, exclude=exclude, max_num=max_num)
    FormSet.ct_field = ct_field
    FormSet.ct_fk_field = fk_field
    return FormSet

class TranslationInlineModelAdmin(InlineModelAdmin):
    model=Translation
    ct_field = "content_type"
    ct_fk_field = "object_id"
    form = TranslationForm
    formset = BaseTranslationInlineFormSet

    def get_formset(self, request, obj=None):
        if self.declared_fieldsets:
            fields = flatten_fieldsets(self.declared_fieldsets)
        else:
            fields = None

        defaults = {
            "ct_field": self.ct_field,
            "fk_field": self.ct_fk_field,
            "form": self.form,
            "formfield_callback": self.formfield_for_dbfield,
            "formset": self.formset,
            "extra": self.extra,
            "can_delete": self.can_delete,
            "can_order": False,
            "fields": fields,
            "max_num": self.max_num,
            "exclude": self.exclude
        }
        return translation_inlineformset_factory(self.model, **defaults)

class TranslationStackedInline(TranslationInlineModelAdmin):
    template = 'admin/edit_inline/stacked.html'

class TranslationTabularInline(TranslationInlineModelAdmin):
    template = 'admin/edit_inline/tabular.html'
