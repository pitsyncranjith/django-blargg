from datetime import datetime

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.utils.safestring import mark_safe


class TagManager(models.Manager):
    def create_tags(self, entry):
        """Inspects an ``Entry`` instance, and builds associates ``Tag``
        objects based on the values in the ``Entry``'s ``tag_string``."""
        tag_list = [t.lower().strip() for t in entry.tag_string.split(',')]
        for t in tag_list:
            try:
                # only add the tag if it's not aleady associated with the entry
                tag_obj, created = self.get_or_create(name=t)
                if tag_obj.name not in entry.tags.values_list('name', flat=True):
                    entry.tags.add(tag_obj)
            except IntegrityError:
                pass  # just ignore any tags that are duplicates


class Tag(models.Model):
    """A *really* light-weight tagging class."""
    name = models.CharField(max_length=256)
    slug = models.SlugField(max_length=256, editable=False, unique=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

    def save(self, *args, **kwargs):
        """Generate a unique slug for each tag."""
        self.name = self.name.lower().strip()
        self.slug = slugify(self.name)
        super(Tag, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('tagged_entry_list', args=[self.slug])

    objects = TagManager()


class Entry(models.Model):
    CONTENT_FORMAT_CHOICES = (
        ('html', 'HTML'),
        ('md', 'Markdown (not yet supported)'),
        ('rst', 'reStructured Text (not yet supported)'),
    )

    site = models.ForeignKey(Site)
    author = models.ForeignKey(User)
    title = models.CharField(max_length=256)

    raw_content = models.TextField(help_text="Content entered by the author.")
    content_format = models.CharField(max_length=4,
        choices=CONTENT_FORMAT_CHOICES)
    rendered_content = models.TextField(editable=False)

    published = models.BooleanField(default=False, blank=True,
        help_text="Show this entry to the public")
    slug = models.SlugField(max_length=255, unique=True,
        help_text="A slug/url used to identify this entry.")
    date_slug = models.SlugField(max_length=255, unique=True, editable=False,
        help_text="A slug/url used to identify this entry; also includes "
                  "the date on which the entry was published.")

    tag_string = models.TextField(blank=True,
        help_text="A comma-separated list of tags.")
    tags = models.ManyToManyField(Tag, editable=False)

    published_on = models.DateTimeField(blank=True, null=True, editable=False)
    updated_on = models.DateTimeField(auto_now=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return self.title

    class Meta:
        ordering = ['-published_on', 'title']
        get_latest_by = 'published_on'
        verbose_name = 'Entry'
        verbose_name_plural = 'Entries'

    def _create_slug(self):
        """Generates a slug from the Title."""
        # Don't overwrite any existing slugs by default.
        if not self.slug:
            self.slug = slugify(self.title)

    def _create_date_slug(self):
        """Prefixes the slug with the ``published_on`` date."""
        if not self.pk:
            # haven't saved this yet, so use today's date
            d = datetime.today()
        elif self.published and self.published_on:
            # use the actual published on date
            d = self.published_on
        elif self.updated_on:
            # default to the last-updated date
            d = self.updated_on
        self.date_slug = u"{0}/{1}".format(d.strftime("%Y/%m/%d"), self.slug)

    def _render_content(self):
        """Renders the content according to the ``content_format``."""
        if self.content_format == "html":
            self.rendered_content = self.raw_content
        elif self.content_format == "md":
            raise NotImplementedError  # TODO: run thru markdown!
            self.rendered_content = self.raw_content
        elif self.content_fromat == "rst":
            raise NotImplementedError  # TODO: run thru markdown!
            self.rendered_content = self.raw_content

    def _set_published(self):
        """Just set the fields that need to be set in order for this thing to
        appear "Published"."""
        self.published = True
        self.published_on = datetime.now()

    def save(self, *args, **kwargs):
        """Auto-generate a slug from the name."""
        self._create_slug()
        self._create_date_slug()
        self._render_content()
        # Make sure we set a `published_on` date if we publish this at
        # creation time.
        if not self.id and self.published:
            self._set_published()
        super(Entry, self).save(*args, **kwargs)

    def get_absolute_url(self):
        if self.published_on:
            args = [
                self.published_on.strftime("%Y"),
                self.published_on.strftime("%m"),
                self.published_on.strftime("%d"),
                self.slug
            ]
        else:
            args = [self.slug]
        return reverse('entry_detail', args=args)

    def publish(self):
        """Puplish & Save."""
        self._set_published()
        self.save()

    def unpublish(self):
        self.published = False
        self.published_on = None
        self.save()

    @property
    def content(self):
        safe_content = mark_safe(self.rendered_content)
        return safe_content

@receiver(post_save, sender=Entry, dispatch_uid='generate-entry-tags')
def generate_entry_tags(sender, instance, created, raw, using, **kwargs):
    """Generate the M2M ``Tag``s for an ``Entry`` right after it has
    been saved."""
    Tag.objects.create_tags(instance)
