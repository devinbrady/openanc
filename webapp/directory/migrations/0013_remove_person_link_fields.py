from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0012_copy_person_links'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='historicalperson',
            name='facebook_link',
        ),
        migrations.RemoveField(
            model_name='historicalperson',
            name='mastodon_link',
        ),
        migrations.RemoveField(
            model_name='historicalperson',
            name='twitter_link',
        ),
        migrations.RemoveField(
            model_name='historicalperson',
            name='website_link',
        ),
        migrations.RemoveField(
            model_name='person',
            name='facebook_link',
        ),
        migrations.RemoveField(
            model_name='person',
            name='mastodon_link',
        ),
        migrations.RemoveField(
            model_name='person',
            name='twitter_link',
        ),
        migrations.RemoveField(
            model_name='person',
            name='website_link',
        ),
    ]
