from urllib.parse import urlsplit

from django.db import migrations

# Old per-network columns, in the order the ANC page used to list them.
OLD_FIELDS = ['anc_homepage_link', 'twitter_link']
TWITTER_HOSTS = {'twitter.com', 'www.twitter.com', 'x.com', 'www.x.com', 'mobile.twitter.com'}


def copy_links(apps, schema_editor):
    """Move each ANC's old link columns into ANCLink rows. Twitter/X links start unpublished,
    matching how person links were migrated."""
    ANC = apps.get_model('directory', 'ANC')
    ANCLink = apps.get_model('directory', 'ANCLink')
    links = []
    for anc in ANC.objects.order_by('id'):
        seen = set()
        for field in OLD_FIELDS:
            url = getattr(anc, field).strip()
            if not url or url in seen:
                continue
            seen.add(url)
            is_twitter = (urlsplit(url).hostname or '').lower() in TWITTER_HOSTS
            links.append(ANCLink(anc_id=anc.id, url=url, publish=not is_twitter))
    ANCLink.objects.bulk_create(links)


def restore_links(apps, schema_editor):
    """Reverse: put each ANC's first link per network back into the old columns."""
    ANCLink = apps.get_model('directory', 'ANCLink')
    for link in ANCLink.objects.select_related('anc').order_by('position', 'id'):
        anc = link.anc
        host = (urlsplit(link.url).hostname or '').lower()
        field = 'twitter_link' if host in TWITTER_HOSTS else 'anc_homepage_link'
        if not getattr(anc, field):
            setattr(anc, field, link.url)
            anc.save(update_fields=[field])
    ANCLink.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0016_anclink'),
    ]

    operations = [
        migrations.RunPython(copy_links, restore_links),
    ]
