#!/usr/bin/env python
# -*- coding: utf-8 -*-
from string import ascii_letters
from random import choice

from mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import TestCase
from django.utils.timezone import now as utc_now

from ..models import Tag, Entry


class TestTagManager(TestCase):

    def setUp(self):
        username = ''.join([choice(ascii_letters) for i in range(10)])
        user = User.objects.create(
            username=username,
            password='{0}@example.com'.format(username)
        )
        self.entry = Entry(
            site=Site.objects.get(pk=settings.SITE_ID),
            author=user,
            title="Test Entry",
            raw_content="Test Content",
            tag_string="foo, bar, baz",
        )

    def test_create_tags(self):
        """This kinda sucks, but saving an entry triggers a signal that then
        creates tags via TagManager

        Entry.save()
            -> generate_entry_tags()
                -> Tag.objects.create_tags(entry)

        """
        # No Tags yet...
        self.assertEqual(Tag.objects.all().count(), 0)
        # Save the Entry
        self.entry.save()
        # We should have tags!
        self.assertEqual(Tag.objects.all().count(), 3)


class TestTag(TestCase):
    urls = "blargg.urls"

    def setUp(self):
        self.tag = Tag(name="Test Tag")
        self.tag.save()

    def test__unicode__(self):
        self.assertEqual(self.tag.__unicode__(), u"test tag")

    def test_save(self):
        """Verify that tag names get lowercased & stripped, while slugs are
        slugified."""
        t = Tag(name="   Foo Tag   ")
        self.assertEqual(t.slug, '')
        t.save()
        self.assertEqual(t.name, u"foo tag")
        self.assertEqual(t.slug, u"foo-tag")

    def test_get_absolute_url(self):
        self.assertIn("tags/test-tag/", self.tag.get_absolute_url())


class TestEntry(TestCase):

    def setUp(self):
        # patch the utc_now function so it's return value is essentiall cashed
        self.now = utc_now()
        config = {'return_value': self.now}
        self.utc_now_patcher = patch('blargg.models.utc_now', **config)
        self.utc_now_patcher.start()

        username = ''.join([choice(ascii_letters) for i in range(10)])
        user = User.objects.create(
            username=username,
            password='{0}@example.com'.format(username)
        )
        self.entry = Entry(
            site=Site.objects.get(pk=settings.SITE_ID),
            author=user,
            title="Test Entry",
            raw_content="Test Content",
            tag_string="foo, bar, baz",
        )
        self.entry.save()

    def tearDown(self):
        self.utc_now_patcher.stop()

    def test__unicode__(self):
        self.assertEqual(self.entry.__unicode__(), self.entry.title)

    def test__create_slug(self):
        e = Entry(title="Foo Bar")
        e._create_slug()
        self.assertEqual(e.slug, "foo-bar")

    def test__create_date_slug_new(self):
        # The expected ``date_slug`` value
        date_slug = "{0}/{1}".format(self.now.strftime("%Y/%m/%d"), "test")

        # When entry is a new object (calls utc_now)
        e = Entry(title="test", slug="test")
        e._create_date_slug()
        self.assertEqual(e.date_slug, date_slug)

    def test__create_date_slug_published(self):
        # The expected ``date_slug`` value
        date_slug = "{0}/{1}".format(self.now.strftime("%Y/%m/%d"),
            self.entry.slug)

        # When entry is published (use the published_on date)
        self.entry.published = True
        self.entry.published_on = self.now
        self.entry._create_date_slug()
        self.assertEqual(self.entry.date_slug, date_slug)

    def test__create_date_slug_unpublished(self):
        # When entry is not published (use the updated_on date)
        self.entry.published = False
        self.entry.save()  # save to get an updated_on
        date_slug = "{0}/{1}".format(
            self.entry.updated_on.strftime("%Y/%m/%d"),
            self.entry.slug
        )
        self.entry._create_date_slug()
        self.assertEqual(self.entry.date_slug, date_slug)

    def test__render_content_html(self):
        self.entry.content_format = "html"
        self.entry._render_content()
        self.assertEqual(self.entry.raw_content, self.entry.rendered_content)

    def test__render_content_rst(self):
        self.entry.content_format = "rst"
        self.entry._render_content()
        self.assertEqual(self.entry.rendered_content, "<p>Test Content</p>\n")

    def test__render_content_md(self):
        with self.assertRaises(NotImplementedError):
            self.entry.content_format = "md"
            self.entry._render_content()

    def test__set_published(self):
        self.assertFalse(self.entry.published)
        self.assertEqual(self.entry.published_on, None)
        self.entry._set_published()
        self.assertTrue(self.entry.published)
        self.assertEqual(self.entry.published_on, self.now)

    def test_save(self):
        self.entry._create_slug = Mock()
        self.entry._create_date_slug = Mock()
        self.entry._render_content = Mock()
        self.entry._set_published = Mock()

        self.entry.save()

        self.entry._create_slug.assert_called_once_with()
        self.entry._create_date_slug.assert_called_once_with()
        self.entry._render_content.assert_called_once_with()
        # Entry was not published, so ``_set_published`` should not get called
        self.assertFalse(self.entry._set_published.called)

        self.entry.published = True
        self.entry.save()
        self.entry._set_published.assert_called_once_with()

    def test_get_absolute_url(self):
        # If not published /blog/slug/
        self.assertIn(self.entry.slug, self.entry.get_absolute_url())

        # If published, /blog/yyyy/mm/dd/slug/
        self.entry.publish()
        url = "{0}/{1}".format(self.now.strftime("%Y/%m/%d"), self.entry.slug)
        self.assertIn(url, self.entry.get_absolute_url())

    @patch.object(Entry, "_set_published")
    def test_publish(self, mock_set_published):
        self.entry.publish()
        mock_set_published.asserted_called_once_with()

    @patch.object(Entry, "save")
    def test_unpublish(self, mock_save):
        self.entry.unpublish()
        self.assertFalse(self.entry.published)
        self.assertEqual(self.entry.published_on, None)
        mock_save.assert_called_once_with()

    def test_content(self):
        with patch("blargg.models.mark_safe") as mock_mark_safe:
            mock_mark_safe.return_value = "SAMPLE CONTENT"
            result = self.entry.content
            mock_mark_safe.assert_called_once_with(self.entry.rendered_content)
            self.assertEqual(result, "SAMPLE CONTENT")
        mock_mark_safe.reset_mock()

    def test_crossposted_content(self):
        with patch("blargg.models.mark_safe") as mock_mark_safe:
            mock_mark_safe.return_value = "SAMPLE CONTENT"
            result = self.entry.crossposted_content
            mock_mark_safe.assert_any_call
            self.assertEqual(result, "SAMPLE CONTENT")
        mock_mark_safe.reset_mock()