from urllib.parse import urlsplit

from django.db import migrations

# Old per-network columns, in the order the person page used to list them.
OLD_FIELDS = ['website_link', 'twitter_link', 'mastodon_link', 'facebook_link']
TWITTER_HOSTS = {'twitter.com', 'www.twitter.com', 'x.com', 'www.x.com', 'mobile.twitter.com'}


def copy_links(apps, schema_editor):
    """Move each Person's old link columns into PersonLink rows. Twitter/X links start
    unpublished so they can be reviewed before reappearing on the public site."""
    Person = apps.get_model('directory', 'Person')
    PersonLink = apps.get_model('directory', 'PersonLink')
    links = []
    for person in Person.objects.order_by('id'):
        seen = set()
        for field in OLD_FIELDS:
            url = getattr(person, field).strip()
            if not url or url in seen:
                continue
            seen.add(url)
            is_twitter = (urlsplit(url).hostname or '').lower() in TWITTER_HOSTS
            links.append(PersonLink(person_id=person.id, url=url, publish=not is_twitter))
    PersonLink.objects.bulk_create(links)


def restore_links(apps, schema_editor):
    """Reverse: put each person's first link per network back into the old columns."""
    Person = apps.get_model('directory', 'Person')
    PersonLink = apps.get_model('directory', 'PersonLink')
    hosts = {
        'twitter_link': TWITTER_HOSTS,
        'facebook_link': {'facebook.com', 'www.facebook.com', 'm.facebook.com'},
    }
    for link in PersonLink.objects.select_related('person').order_by('id'):
        person = link.person
        host = (urlsplit(link.url).hostname or '').lower()
        field = next((f for f, hs in hosts.items() if host in hs), 'website_link')
        if not getattr(person, field):
            setattr(person, field, link.url)
            person.save(update_fields=[field])
    PersonLink.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0011_personlink'),
    ]

    operations = [
        migrations.RunPython(copy_links, restore_links),
    ]
